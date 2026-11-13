import { useState, useCallback } from 'react';

function areEqual<T>(a: T, b: T): boolean {
  if (Object.is(a, b)) return true;
  try {
    return JSON.stringify(a) === JSON.stringify(b);
  } catch {
    return false;
  }
}

export function useUndoRedo<T>(initialState: T) {
  const [histState, setHistState] = useState<{ history: T[]; index: number }>({
    history: [initialState],
    index: 0,
  });

  const state = histState.history[histState.index];

  const setParamState = useCallback((newState: T | ((prevState: T) => T)) => {
    setHistState((prev) => {
      const current = prev.history[prev.index];
      const resolvedState =
        typeof newState === 'function' ? (newState as ((prevState: T) => T))(current) : newState;
      if (areEqual(current, resolvedState)) {
        return prev;
      }
      const newHistory = prev.history.slice(0, prev.index + 1);
      newHistory.push(resolvedState);
      return {
        history: newHistory,
        index: newHistory.length - 1,
      };
    });
  }, []);

  const undo = useCallback(() => {
    setHistState((prev) => (prev.index > 0 ? { ...prev, index: prev.index - 1 } : prev));
  }, []);

  const redo = useCallback(() => {
    setHistState((prev) =>
      prev.index < prev.history.length - 1 ? { ...prev, index: prev.index + 1 } : prev
    );
  }, []);

  const reset = useCallback(() => {
    setHistState({ history: [initialState], index: 0 });
  }, [initialState]);

  const setParamStateReplace = useCallback((newState: T | ((prevState: T) => T)) => {
    setHistState((prev) => {
      const current = prev.history[prev.index];
      const resolvedState =
        typeof newState === 'function' ? (newState as ((prevState: T) => T))(current) : newState;
      const newHistory = [...prev.history];
      newHistory[prev.index] = resolvedState;
      return {
        history: newHistory,
        index: prev.index,
      };
    });
  }, []);

  const canUndo = histState.index > 0;
  const canRedo = histState.index < histState.history.length - 1;

  return [state, setParamState, { undo, redo, reset, canUndo, canRedo, setParamStateReplace }] as const;
}
