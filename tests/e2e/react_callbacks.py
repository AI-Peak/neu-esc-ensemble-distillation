"""Test-only adapter for the pinned React 19.2 DOM props representation.

Call the current button's bound callback directly, bypassing React's disabled
event dispatch. Never edit React props or cache a closure across renders. An
unsupported React representation fails loudly; this is not a synthetic click.
"""
import json


def invoke_bound_onclick(button, *, disabled):
    result = button.evaluate(
        """(el, expectedDisabled) => {
          const keys = Object.keys(el).filter(k => k.startsWith('__reactProps$'));
          if (keys.length !== 1) throw new Error('Expected exactly one React props key');
          const props = el[keys[0]];
          if (typeof props.onClick !== 'function') throw new Error('Missing bound onClick');
          if (Boolean(props.disabled) !== expectedDisabled || el.disabled !== expectedDisabled) {
            throw new Error('Unexpected React/DOM disabled state before callback');
          }
          const callback = props.onClick;
          const counts = window.__c1CallbackCounts ??= new WeakMap();
          const before = counts.get(el) ?? 0;
          callback();
          counts.set(el, before + 1);
          if (el[keys[0]] !== props || props.onClick !== callback ||
              Boolean(props.disabled) !== expectedDisabled || el.disabled !== expectedDisabled) {
            throw new Error('Callback adapter changed React props or DOM disabled state');
          }
          return {button: el.textContent.trim(), before, after: counts.get(el),
                  reactDisabled: Boolean(props.disabled), domDisabled: el.disabled};
        }""",
        disabled,
    )
    assert result["after"] == result["before"] + 1, result
    print("C1 bound callback: " + json.dumps(result, ensure_ascii=False))
    # Save's onClick returns void. Its async work is observed by request/UI
    # assertions in the caller, never by awaiting the callback's return value.
    settle_browser(button.page)
    return result


def settle_browser(page):
    """Let fetch continuations, React renders and effects process after delivery."""
    page.evaluate(
        """() => new Promise(resolve => requestAnimationFrame(() =>
          requestAnimationFrame(() => setTimeout(resolve, 0))))"""
    )
