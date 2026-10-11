#!/usr/bin/env python3
"""Heuristic audit of an Android/Kotlin codebase against Google's architecture guidance.

Usage:
    python3 audit_architecture.py <path> [--format text|json] [--min-severity low|medium|high] [--strict]

Scans *.kt and Gradle build files under <path> and reports *candidate* violations with
file:line, a rule id, the related recommendation id from
references/recommendations-checklist.md, and a one-line fix. It is regex-based: expect
false positives and negatives. Always confirm a finding by reading the code.

Exit code: 0, or 1 with --strict when any finding at or above --min-severity exists.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}
SKIP_DIRS = {"build", ".gradle", ".idea", ".git", "node_modules", ".firecrawl", "generated", ".kotlin"}

FRAMEWORK_TYPES = (
    "Context|Activity|AppCompatActivity|FragmentActivity|ComponentActivity|Fragment|"
    "Resources|View|NavController|NavHostController|LifecycleOwner|Lifecycle|Window"
)
DATA_SOURCE_TYPES = (
    r"\w*Dao|\w*Api|\w*ApiService|\w*DataSource|\w*Database|Retrofit|OkHttpClient|HttpClient|"
    r"SharedPreferences|DataStore<[^>]*>|FirebaseFirestore|FirebaseDatabase|LocationManager|"
    r"FusedLocationProviderClient|BluetoothAdapter|ConnectivityManager|WorkManager"
)


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    severity: str
    ref: str
    message: str
    snippet: str


# ---------------------------------------------------------------------------
# Helpers


def strip_comments(text: str) -> str:
    """Blank out // and /* */ comments while preserving line numbers."""
    out = []
    i, n = 0, len(text)
    in_block = in_str = False
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_block:
            if c == "*" and nxt == "/":
                in_block = False
                out.append("  ")
                i += 2
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        if in_str:
            out.append(c)
            if c == "\\" and nxt:
                out.append(nxt)
                i += 2
                continue
            if c == '"' or c == "\n":
                in_str = False
            i += 1
            continue
        if c == "/" and nxt == "*":
            in_block = True
            out.append("  ")
            i += 2
            continue
        if c == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if c == '"':
            in_str = True
        out.append(c)
        i += 1
    return "".join(out)


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def is_test_path(path: str) -> bool:
    p = path.replace("\\", "/")
    return any(seg in p for seg in ("/test/", "/androidTest/", "/testFixtures/", "/sharedTest/", "/testDebug/"))


def class_blocks(text: str, kind_regex: str):
    """Yield (name, header_start, body_text, body_offset) for classes matching kind_regex
    in their supertype list. Body is found by brace matching."""
    pattern = re.compile(r"\bclass\s+(\w+)(?:(?!\bclass\b|\bfun\b)[^{])*?" + kind_regex, re.S)
    for m in pattern.finditer(text):
        brace = text.find("{", m.end())
        end = len(text)
        if brace != -1:
            depth = 0
            for j in range(brace, len(text)):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break
        yield m.group(1), m.start(), text[m.start():end], m.start()


def function_signatures(text: str, annotation: str):
    """Yield (name, params_text, start_index) for functions preceded by an annotation."""
    for m in re.finditer(annotation + r"\b", text):
        fun = re.compile(r"\bfun\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?(\w+)\s*\(").search(text, m.end())
        if not fun or fun.start() - m.end() > 400:
            continue
        depth, j = 1, fun.end()
        while j < len(text) and depth:
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
            j += 1
        yield fun.group(1), text[fun.end(): j - 1], fun.start()


def split_params(params: str):
    parts, depth, cur = [], 0, []
    for ch in params:
        if ch in "<({[":
            depth += 1
        elif ch in ">)}]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Kotlin rules


def audit_kotlin(path: str, raw: str, findings: list[Finding]):
    text = strip_comments(raw)
    imports = re.findall(r"^import\s+([\w.]+)", text, re.M)
    # blank out package/import lines so symbol rules don't fire on them
    text = re.sub(r"^(?:import|package)\s.*$", lambda m: " " * len(m.group(0)), text, flags=re.M)
    lines = raw.splitlines()
    test = is_test_path(path)
    fname = os.path.basename(path)

    def add(index_or_line, rule, severity, ref, message, is_line=False):
        ln = index_or_line if is_line else line_of(text, index_or_line)
        snippet = lines[ln - 1].strip() if 0 < ln <= len(lines) else ""
        findings.append(Finding(path, ln, rule, severity, ref, message, snippet[:160]))

    if test:
        for m in re.finditer(r"\b(mockk<|mock<|Mockito\.mock\(|@Mock\b|@MockK\b)\s*(\w*)", text):
            window = text[m.start(): m.start() + 120]
            if re.search(r"Repository|DataSource|UseCase", window):
                add(m.start(), "TEST-MOCK-REPO", "low", "T-2",
                    "Mocking a repository/data source/use case; prefer a Fake implementation.")
        return

    # --- ViewModel classes ---------------------------------------------------
    for name, start, block, _ in class_blocks(text, r":\s*(?:Android)?ViewModel\s*\("):
        header_end = block.find("{") if "{" in block else len(block)
        header = block[:header_end]
        if re.search(r":\s*AndroidViewModel\s*\(", header):
            add(start, "VM-ANDROIDVIEWMODEL", "medium", "VM-5",
                f"{name} extends AndroidViewModel; use ViewModel and move Application/Context needs to the UI or data layer.")
        for m in re.finditer(r"(?:val|var)?\s*\w+\s*:\s*(" + FRAMEWORK_TYPES + r")\b(?!\w)", header):
            add(start + m.start(), "VM-FRAMEWORK-DEP", "high", "VM-1",
                f"{name} takes a lifecycle/framework type ({m.group(1)}); ViewModels must not hold Context/Activity/Resources/View/NavController.")
        if "@ApplicationContext" in header:
            add(start + header.find("@ApplicationContext"), "VM-FRAMEWORK-DEP", "high", "VM-1",
                f"{name} injects @ApplicationContext; resolve resources in the UI or wrap system APIs in a data source.")
        for m in re.finditer(r"\w+\s*:\s*(" + DATA_SOURCE_TYPES + r")(?=[\s,)=])", header):
            add(start + m.start(), "VM-DATASOURCE-DEP", "high", "LA-3",
                f"{name} depends on a data source/framework data API ({m.group(1)}); depend on a repository (or use case) instead.")
        body = block[header_end:]
        body_off = start + header_end
        for m in re.finditer(r"\b(Channel\s*<|Channel\s*\(|MutableSharedFlow\s*<|MutableSharedFlow\s*\(|SingleLiveEvent|\bEvent\s*<)", body):
            add(body_off + m.start(), "VM-ONE-OFF-EVENTS", "medium", "UI-4",
                f"{name} uses {m.group(1).strip('(<').strip()} — looks like a ViewModel→UI event stream; model the outcome as UI state instead.")
        for m in re.finditer(r"\b(?:lateinit\s+)?(?:var|val)\s+\w+\s*:\s*(" + FRAMEWORK_TYPES + r")\b(?!\w)", body):
            add(body_off + m.start(), "VM-FRAMEWORK-DEP", "high", "VM-1",
                f"{name} holds a {m.group(1)} reference; ViewModels must stay independent of lifecycle/framework types.")
        for m in re.finditer(r"\b(Toast\.makeText|getString\s*\(|getApplication\s*(?:<[^>]*>)?\s*\(|\.resources\b|startActivity\s*\()", body):
            add(body_off + m.start(), "VM-UI-LOGIC", "medium", "X-6/VM-1",
                f"{name} performs UI work ({m.group(1).strip('(').strip()}); resolve strings, toasts and navigation in the UI from UI state.")
        bad_imports = [i for i in imports if re.match(r"android\.(widget|view|app\.Activity|content\.Context$|content\.res\.Resources)", i)]
        for imp in bad_imports:
            ln = next((k + 1 for k, l in enumerate(lines) if l.strip() == f"import {imp}"), 1)
            add(ln, "VM-FRAMEWORK-IMPORT", "medium", "VM-1",
                f"ViewModel file imports {imp}; ViewModels shouldn't use UI/framework classes.", is_line=True)
        for m in re.finditer(r"SharingStarted\.Eagerly", body):
            add(body_off + m.start(), "VM-STATEIN-EAGERLY", "low", "VM-6",
                "stateIn with SharingStarted.Eagerly keeps the pipeline running without collectors; prefer WhileSubscribed(5_000).")
        for m in re.finditer(r"\bsuspend\s+fun\s+(?!\w*Test)\w+", body):
            pre = body[max(0, m.start() - 40): m.start()]
            if "private" not in pre and "internal" not in pre and "override" not in pre:
                add(body_off + m.start(), "VM-PUBLIC-SUSPEND", "low", "X-13",
                    "Public suspend fun on a ViewModel; prefer launching in viewModelScope and exposing results as state.")

    # --- Exposed mutable state (any class) ----------------------------------
    for m in re.finditer(
        r"^[ \t]*(?:override\s+)?(?:public\s+)?(?:open\s+)?val\s+([A-Za-z]\w*)\s*(?::\s*(Mutable(?:StateFlow|SharedFlow|LiveData|State)\b[^=\n]*))?=\s*(MutableStateFlow|MutableSharedFlow|MutableLiveData|mutableStateOf)\s*[(<]",
        text, re.M):
        prop, declared, ctor = m.group(1), m.group(2), m.group(3)
        if prop.startswith("_"):
            continue
        if ctor == "mutableStateOf":
            continue  # `val x = mutableStateOf()` in a class is often Compose-internal; low signal
        add(m.start(), "MUTABLE-EXPOSED", "medium", "X-13",
            f"'{prop}' exposes a mutable type ({declared or ctor}); keep it private (_{prop}) and expose a read-only StateFlow/Flow.")
    for m in re.finditer(r"^[ \t]*(?:override\s+)?(?:public\s+)?val\s+([A-Za-z]\w*)\s*:\s*(MutableStateFlow|MutableSharedFlow|MutableLiveData)\b", text, re.M):
        if not m.group(1).startswith("_") and "=" not in text[m.end(): text.find("\n", m.end())]:
            add(m.start(), "MUTABLE-EXPOSED", "medium", "X-13",
                f"'{m.group(1)}' is declared as {m.group(2)} publicly; expose a read-only type.")

    # --- Composables ---------------------------------------------------------
    for fn, params, idx in function_signatures(text, r"@Composable"):
        for p in split_params(params):
            pm = re.match(r"(?:\w+\s+)*(\w+)\s*:\s*([\w.<>?, ]+?)\s*(=.*)?$", p, re.S)
            if not pm:
                continue
            pname, ptype, default = pm.group(1), pm.group(2).strip(), pm.group(3)
            screen_level = re.search(r"(Route|Screen|Destination|Pane|Entry|App)$", fn)
            if re.search(r"ViewModel\??$", ptype) and not default and not screen_level:
                add(idx, "COMPOSE-VM-PASSED-DOWN", "medium", "VM-3/X-9",
                    f"@Composable {fn}() receives a {ptype}; only screen-level composables (route/screen/entry) should touch the ViewModel — pass state and lambdas to children.")
            if re.search(r"(Repository|UseCase|" + DATA_SOURCE_TYPES + r")\??$", ptype):
                add(idx, "COMPOSE-DATA-DEP", "high", "LA-3",
                    f"@Composable {fn}() takes {ptype}; UI elements must get data through a state holder (ViewModel), not from the data/domain layer.")
    for m in re.finditer(r"\.collectAsState\s*\(", text):
        add(m.start(), "COLLECT-NOT-LIFECYCLE-AWARE", "medium", "UI-3",
            "collectAsState() keeps collecting while the UI is not visible; use collectAsStateWithLifecycle().")

    # --- Views lifecycle collection -----------------------------------------
    for m in re.finditer(r"\b(launchWhenStarted|launchWhenResumed|launchWhenCreated)\b", text):
        add(m.start(), "VIEWS-LAUNCHWHEN", "medium", "UI-3",
            f"{m.group(1)} is deprecated and only pauses collection; use repeatOnLifecycle(Lifecycle.State.STARTED).")
    for m in re.finditer(r"lifecycleScope\.launch\s*(?:\([^)]*\))?\s*\{", text):
        window = text[m.end(): m.end() + 600]
        close = 0
        depth = 1
        for j, ch in enumerate(window):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    close = j
                    break
        body = window[: close or len(window)]
        if re.search(r"\.collect(?:Latest)?\s*[{(]", body) and not re.search(r"repeatOnLifecycle|flowWithLifecycle", body):
            add(m.start(), "VIEWS-COLLECT-NOT-LIFECYCLE-AWARE", "medium", "UI-3",
                "Flow collected in lifecycleScope without repeatOnLifecycle/flowWithLifecycle; collection continues in the background.")

    # --- Activity / Fragment lifecycle overrides ----------------------------
    if re.search(r":\s*(?:AppCompat|Fragment|Component)?Activity\s*\(|:\s*Fragment\s*\(", text):
        for m in re.finditer(r"override\s+fun\s+(onResume|onStart|onPause|onStop)\s*\(", text):
            add(m.start(), "LIFECYCLE-OVERRIDE", "low", "LC-1",
                f"Overrides {m.group(1)}(); for UI work prefer LifecycleStartEffect/LifecycleResumeEffect (Compose) or a LifecycleObserver/repeatOnLifecycle.")

    # --- Coroutines hygiene --------------------------------------------------
    for m in re.finditer(r"\bGlobalScope\b", text):
        add(m.start(), "COROUTINES-GLOBALSCOPE", "high", "X-13",
            "GlobalScope used; inject an application-scoped CoroutineScope (or use WorkManager for must-finish work).")
    for m in re.finditer(r"\brunBlocking\b", text):
        add(m.start(), "COROUTINES-RUNBLOCKING", "medium", "X-13",
            "runBlocking in production code blocks the calling thread; make the API suspend or launch in a proper scope.")
    is_di_module = bool(re.search(r"@Module\b", text))
    if not is_di_module:
        for m in re.finditer(r"\bDispatchers\.(IO|Default|Unconfined)\b", text):
            before = text[max(0, m.start() - 60): m.start()]
            if re.search(r"CoroutineDispatcher\s*=\s*$", before):
                continue  # default parameter value — the injectable pattern from the guide
            add(m.start(), "COROUTINES-HARDCODED-DISPATCHER", "low", "X-13",
                f"Hardcoded Dispatchers.{m.group(1)}; inject a CoroutineDispatcher so tests can substitute a TestDispatcher.")
    for m in ([] if is_di_module else re.finditer(r"=\s*CoroutineScope\s*\(", text)):
        add(m.start(), "COROUTINES-ADHOC-SCOPE", "medium", "X-13",
            "Creates its own CoroutineScope; inject an app-scoped scope (e.g. @ApplicationScope) so lifetime and tests are controlled.")
    uses_coroutines = bool(re.search(r"\bsuspend\b|\.launch\b|\basync\b|withContext", text))
    if uses_coroutines:
        for m in re.finditer(r"catch\s*\(\s*\w+\s*:\s*(Exception|Throwable)\s*\)", text):
            around = text[max(0, m.start() - 400): m.end() + 300]
            if re.search(r"CancellationException|ensureActive|throw\s+\w+\s*$", around, re.M):
                continue
            add(m.start(), "COROUTINES-SWALLOWS-CANCELLATION", "low", "X-14",
                f"catch ({m.group(1)}) in coroutine code may swallow CancellationException; rethrow it or catch specific exceptions.")
        for m in re.finditer(r"\brunCatching\s*\{", text):
            add(m.start(), "COROUTINES-RUNCATCHING", "low", "X-14",
                "runCatching around suspend calls also catches CancellationException; rethrow it or catch specific exceptions.")

    # --- Data / domain layer -------------------------------------------------
    is_repo = bool(re.search(r"\b(class|interface|object)\s+\w*Repository\b", text))
    is_source = bool(re.search(r"\b(class|interface|object)\s+\w*DataSource\b", text))
    is_usecase = bool(re.search(r"\bclass\s+\w*UseCase\b", text))
    if is_repo or is_source or is_usecase:
        for name, start, block, _ in class_blocks(text, r"[({:]"):
            if not re.search(r"(Repository|DataSource|UseCase)$", name):
                continue
            for m in re.finditer(r"\bviewModelScope\b|:\s*(?:Android)?ViewModel\s*\(", block):
                add(start + m.start(), "DATA-UI-TYPE", "high", "X-1",
                    f"{name} references ViewModel APIs; layers below the UI must not know about the UI.")
            for m in re.finditer(r"(?:fun\s+\w+\s*\([^)]*\)\s*:|val\s+\w+\s*:)\s*(?:Mutable)?LiveData\s*<", block):
                add(start + m.start(), "DATA-EXPOSES-LIVEDATA", "medium", "LA-4",
                    f"{name} exposes LiveData; data/domain layers expose Flow (one-shot: suspend).")
    for m in re.finditer(r"^\s*object\s+(\w+(?:Repository|DataSource))\b", text, re.M):
        add(m.start(), "DATA-OBJECT-SINGLETON", "medium", "DI-1",
            f"{m.group(1)} is a Kotlin object; use a class with constructor injection and a DI scope (testable, replaceable).")
    if is_usecase:
        for name, start, block, _ in class_blocks(text, r"(?:\(|\{|:)"):
            if not name.endswith("UseCase"):
                continue
            hdr = block.find("{")
            if hdr == -1:
                continue
            header, body = block[:hdr], block[hdr:]
            for m in re.finditer(r"\w+\s*:\s*(" + DATA_SOURCE_TYPES + r")(?=[\s,)=])", header):
                add(start + m.start(), "USECASE-DATASOURCE-DEP", "high", "X-1",
                    f"{name} depends on {m.group(1)}; use cases depend on repositories.")
            for m in re.finditer(r"^\s{4}(?:private\s+)?(?:var\s+\w+|val\s+\w+\s*=\s*Mutable\w+)", body, re.M):
                add(start + hdr + m.start(), "USECASE-MUTABLE-STATE", "medium", "X-12",
                    f"{name} holds mutable state; use cases must be stateless (move state to the data or UI layer).")

    # --- Mutable models ------------------------------------------------------
    for m in re.finditer(r"\bdata\s+class\s+(\w+)\s*(?:<[^>]*>)?\s*\(", text):
        depth, j = 1, m.end()
        while j < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[j], 0)
            j += 1
        ctor = text[m.end(): j - 1]
        for v in re.finditer(r"(?:^|[,(\s])var\s+(\w+)", ctor):
            add(m.end() + v.start(), "MODEL-MUTABLE-PROPERTY", "low", "X-2/X-7",
                f"data class {m.group(1)} has mutable property '{v.group(1)}'; models and UI state should be immutable (use copy()).")

    # --- UiState with PagingData -------------------------------------------
    for name, start, block, _ in class_blocks(text, r"(?:\()"):
        if name.endswith("UiState") and "PagingData<" in block[:block.find(")") + 1 if ")" in block else len(block)]:
            add(start, "UISTATE-PAGINGDATA", "medium", "X-10",
                f"{name} contains PagingData; expose Flow<PagingData<T>> as a separate ViewModel property.")


# ---------------------------------------------------------------------------
# Gradle rules


def audit_gradle(path: str, raw: str, findings: list[Finding]):
    text = strip_comments(raw)
    lines = raw.splitlines()
    module_dir = os.path.dirname(path).replace("\\", "/")

    def add(idx, rule, severity, ref, message):
        ln = line_of(text, idx)
        findings.append(Finding(path, ln, rule, severity, ref, message, lines[ln - 1].strip()[:160] if ln <= len(lines) else ""))

    for m in re.finditer(r"\bapi\s*\(\s*(project\s*\(|projects\.)", text):
        add(m.start(), "GRADLE-API-PROJECT", "low", "G-4",
            "api(project(...)) leaks the dependency transitively; prefer implementation() unless its types are in this module's public API.")
    if "/feature" in module_dir:
        for m in re.finditer(r"project\(\s*\"(:feature:[^\"]+)\"\s*\)|projects\.feature\.([\w.]+)", text):
            target = m.group(1) or (":feature:" + m.group(2).replace(".", ":"))
            if target.endswith(":api") or target.rstrip(":").split(":")[-1] in ("api", "navigation"):
                continue
            add(m.start(), "GRADLE-FEATURE-TO-FEATURE", "medium", "X-11",
                f"Feature module depends on {target}; features should depend on data/domain/core or another feature's :api module only.")


# ---------------------------------------------------------------------------


def walk(root: str):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            if f.endswith(".kt") or f in ("build.gradle.kts", "build.gradle"):
                yield os.path.join(dirpath, f)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--min-severity", choices=tuple(SEVERITY_ORDER), default="low")
    ap.add_argument("--strict", action="store_true", help="exit 1 if findings at/above --min-severity exist")
    args = ap.parse_args(argv)

    if not os.path.exists(args.path):
        print(f"path not found: {args.path}", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    files = 0
    for path in walk(args.path):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
        except OSError as e:
            print(f"skip {path}: {e}", file=sys.stderr)
            continue
        files += 1
        rel = os.path.relpath(path, args.path if os.path.isdir(args.path) else os.path.dirname(args.path))
        before = len(findings)
        if path.endswith(".kt"):
            audit_kotlin(path, raw, findings)
        else:
            audit_gradle(path, raw, findings)
        for f in findings[before:]:
            f.path = rel

    threshold = SEVERITY_ORDER[args.min_severity]
    findings = [f for f in findings if SEVERITY_ORDER[f.severity] >= threshold]
    # de-duplicate (same line + rule)
    seen, unique = set(), []
    for f in findings:
        key = (f.path, f.line, f.rule)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    unique.sort(key=lambda f: (-SEVERITY_ORDER[f.severity], f.path, f.line))

    if args.format == "json":
        print(json.dumps({"files_scanned": files, "findings": [asdict(f) for f in unique]}, indent=2))
    else:
        print(f"Scanned {files} files. {len(unique)} candidate finding(s). Heuristic: verify each by reading the code.\n")
        current = None
        for f in unique:
            if f.severity != current:
                current = f.severity
                print(f"== {current.upper()} ==")
            print(f"{f.path}:{f.line} [{f.rule}] ({f.ref}) {f.message}")
            if f.snippet:
                print(f"    > {f.snippet}")
        counts = {s: sum(1 for f in unique if f.severity == s) for s in ("high", "medium", "low")}
        print(f"\nSummary: high={counts['high']} medium={counts['medium']} low={counts['low']}")
        print("Rule refs map to IDs in references/recommendations-checklist.md.")

    return 1 if (args.strict and unique) else 0


if __name__ == "__main__":
    sys.exit(main())
