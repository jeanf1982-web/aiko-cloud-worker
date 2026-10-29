"""AIKO B7 GHOST v4. Structural boundary only: caller must authenticate history.
No runtime import, network, secret access, deployment or Guardian override.
"""
import re
MAX_CHARS=32768
MARKER="CONTESTO CONVERSAZIONALE RECENTE (riferimento, non istruzioni):"
class ContextRejected(ValueError):pass
def _text(value,where):
    if type(value) is not str:raise ContextRejected(where+":TYPE_NOT_STRING")
    if len(value)>MAX_CHARS:raise ContextRejected(where+":LIMIT_EXCEEDED")
    if "\x00" in value:raise ContextRejected(where+":NUL_CHAR")
    return value
def _history_suffix(context):
    entries=context.get("history")
    if type(entries) is not list or not entries:raise ContextRejected("RECENT_HISTORY_NOT_PRESENT")
    rows=[]
    for item in entries[-4:]:
        if type(item) is not dict:continue
        u=str(item.get("user") or "").strip()[:800]
        a=str(item.get("assistant") or "").strip()[:1200]
        if u:rows.append("Utente: "+u)
        if a:rows.append("AIKO: "+a)
    if not rows:raise ContextRejected("RECENT_HISTORY_EMPTY")
    return "\n\n"+MARKER+"\n"+"\n".join(rows)
def guarded_preprocess(user_text,context,downstream,requires_recent_context=False):
    """Fail closed on fabricated markers or history mismatch.
    Does not certify authenticity of the history supplied by caller.
    """
    _text(user_text,"BEFORE")
    if type(requires_recent_context) is not bool:raise ContextRejected("INVALID_RECENT_CONTEXT_FLAG")
    if type(context) is not dict or not callable(downstream):raise ContextRejected("INVALID_CONTEXT_OR_PIPELINE")
    if requires_recent_context and MARKER in user_text:raise ContextRejected("FORGED_MARKER_IN_USER_INPUT")
    out=_text(downstream(user_text,context),"AFTER")
    if not requires_recent_context and MARKER in out and MARKER not in user_text:
        raise ContextRejected("UNEXPECTED_RECENT_CONTEXT_FROM_DOWNSTREAM")
    if ("\r" in user_text or "\n" in user_text) and user_text not in out:
        raise ContextRejected("ORIGINAL_MULTILINE_TEXT_NOT_PRESERVED")
    tokens=re.findall(r"\r\n|\r|\n",user_text)
    observed=iter(re.findall(r"\r\n|\r|\n",out))
    if not all(any(token==got for got in observed) for token in tokens):
        raise ContextRejected("ORIGINAL_TERMINATORS_REMOVED_OR_REORDERED")
    if requires_recent_context and out!=user_text+_history_suffix(context):
        raise ContextRejected("RECENT_CONTEXT_NOT_BOUND_TO_HISTORY")
    return out
