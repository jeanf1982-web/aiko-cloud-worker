"""AIKO-only: generate sandbox code on a free GitHub Models runner.

Single inference attempt; no private input, ACER compute or paid fallback.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

OUT = Path("artifacts/aiko-growth-models")
MODEL = "openai/gpt-4o-mini"
ENDPOINT = "https://models.github.ai/inference/chat/completions"
PROMPT = """Create ONLY Python source code for a deterministic AIKO text plugin.
def preprocess(user_text,context=None) -> str: return original user_text unchanged.
def postprocess(user_text,reply_text,context=None) -> str: uppercase reply only
if the user explicitly says 'rispondi in maiuscolo' or
'scrivi tutto in maiuscolo' (ignore casing). Otherwise preserve reply.
def self_test() -> dict: {'ok': bool} testing trigger and neutral cases.

Allowed import: re. No filesystem, shell, network, OS, environment, eval,
exec, dynamic imports, classes, decorators or model deployment. Return code only.
"""
FORBIDDEN_NAMES = set(("exec", "eval", "compile", "__import__", "open",
                       "breakpoint", "input", "globals", "locals",
                       "vars", "dir", "getattr", "setattr", "delattr"))
FORBIDDEN_TYPES = (ast.ClassDef, ast.AsyncFunctionDef, ast.With, ast.AsyncWith,
                   ast.Try, ast.Raise, ast.Global, ast.Nonlocal, ast.Lambda,
                   ast.Yield, ast.YieldFrom, ast.Await, ast.Delete)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def receipt_save(data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "generation_receipt.json").write_text(
        json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf8")


def validate(code):
    if not code or len(code) > 8000:
        raise ValueError("BAD_SOURCE_SIZE")
    tree = ast.parse(code)
    funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if not {"preprocess", "postprocess", "self_test"}.issubset(funcs):
        raise ValueError("MISSING_PLUGIN_FUNCTIONS")
    for item in ast.walk(tree):
        if isinstance(item, FORBIDDEN_TYPES):
            raise ValueError("FORBIDDEN_SYNTAX")
        if isinstance(item, (ast.Import, ast.ImportFrom)):
            if isinstance(item, ast.ImportFrom) or any(a.name != "re" for a in item.names):
                raise ValueError("FORBIDDEN_IMPORT")
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Name):
            if item.func.id in FORBIDDEN_NAMES:
                raise ValueError("FORBIDDEN_CALL")
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.FunctionDef)):
            continue
        if isinstance(n, ast.Assign) and isinstance(n.value, (ast.Constant, ast.Dict, ast.Tuple)):
            continue
        raise ValueError("FORBIDDEN_MODULE_TOP_LEVEL")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("CLOUD_RUNNER_ONLY")
    if os.environ.get("GITHUB_REPOSITORY") != "jeanf1982-web/aiko-cloud-worker":
        raise SystemExit("FOREIGN_REPOSITORY")
    if os.environ.get("GITHUB_REF") != "refs/heads/aiko-growth-github-models-sandbox-20261021":
        raise SystemExit("SANDBOX_BRANCH_ONLY")
    receipt = {
        "schema": "AIKO_GITHUB_MODELS_GROWTH_CANDIDATE_V1",
        "project": "AIKO",
        "model": MODEL,
        "repository": os.environ["GITHUB_REPOSITORY"],
        "head_sha": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "prompt_sha256": sha(PROMPT.encode()),
        "status": "NOT_RUN",
        "model_generated": False,
        "private_data_transferred": False,
        "boom_access": False,
        "acer_compute_used": False,
        "production_deployment": False,
        "certified_2_of_2": False,
        "paid_fallback_enabled": False,
    }
    token = os.environ.get("GH_MODELS_TOKEN", "")
    if not token:
        receipt["status"] = "HOLD_TOKEN_UNAVAILABLE"
        receipt_save(receipt)
        print("AIKO_GROWTH_MODEL_HOLD TOKEN_UNAVAILABLE")
        return
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Output safe Python source code only."},
            {"role": "user", "content": PROMPT},
        ],
        "temperature": 0.1,
        "max_tokens": 680,
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            result = json.loads(response.read(20000))
    except urllib.error.HTTPError as exc:
        receipt["status"] = "HOLD_MODEL_HTTP_" + str(exc.code)
        receipt_save(receipt)
        print("AIKO_GROWTH_MODEL_HOLD HTTP_" + str(exc.code))
        return
    except (TimeoutError, OSError, ValueError):
        receipt["status"] = "HOLD_MODEL_NETWORK_OR_FORMAT"
        receipt_save(receipt)
        print("AIKO_GROWTH_MODEL_HOLD NETWORK_OR_FORMAT")
        return
    generated = str((((result.get("choices") or [{}])[0].get("message") or {})
                     .get("content") or "")).strip()
    ticks = chr(96) * 3
    if generated.startswith(ticks):
        generated = re.sub(r"^" + re.escape(ticks) + r"(?:python)?\s*", "", generated)
        generated = re.sub(r"\s*" + re.escape(ticks) + r"$", "", generated)
    receipt["response_sha256"] = sha(generated.encode())
    try:
        validate(generated)
    except (ValueError, SyntaxError):
        receipt["status"] = "REJECTED_STATIC_VALIDATION"
        receipt_save(receipt)
        print("AIKO_GROWTH_MODEL_CANDIDATE_REJECTED")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    candidate = generated.rstrip() + "\n"
    (OUT / "candidate.py").write_text(candidate, encoding="utf8")
    receipt["status"] = "GENERATED_PENDING_INDEPENDENT_TEST"
    receipt["model_generated"] = True
    receipt["candidate_sha256"] = sha(candidate.encode())
    receipt["response_model"] = result.get("model")
    receipt_save(receipt)
    print("AIKO_GROWTH_MODEL_CANDIDATE_GENERATED", receipt["candidate_sha256"])


if __name__ == "__main__":
    main()
