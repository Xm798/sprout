import { useEffect, useRef, useState } from "react";

// Returns a value that only updates after `delay` ms have passed without a
// change. Structural equality (JSON) drives the reset so callers can pass a
// fresh object/array each render — a new identity that serializes the same
// won't restart the timer or emit a new debounced value.
export function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  const key = JSON.stringify(value);
  const latest = useRef(value);
  latest.current = value;

  useEffect(() => {
    const id = setTimeout(() => setDebounced(latest.current), delay);
    return () => clearTimeout(id);
  }, [key, delay]);

  return debounced;
}
