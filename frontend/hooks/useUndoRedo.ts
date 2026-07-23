import { useState, useCallback } from 'react';

export function useUndoRedo<T>(initialState: T) {
  const [history, setHistory] = useState<T[]>([initialState]);
  const [currentIndex, setCurrentIndex] = useState<number>(0);

  const state = history[currentIndex];

  const setParamState = useCallback((newState: T | ((prevState: T) => T)) => {
    setHistory((prevHistory) => {
      const prev = prevHistory[currentIndex];
      const resolvedState = typeof newState === 'function' ? (newState as ((prevState: T) => T))(prev) : newState;
      const newHistory = prevHistory.slice(0, currentIndex + 1);
      newHistory.push(resolvedState);
      return newHistory;
    });
    setCurrentIndex((prevIndex) => prevIndex + 1);
  }, [currentIndex]);

  const undo = useCallback(() => {
    if (currentIndex > 0) {
      setCurrentIndex((prev) => prev - 1);
    }
  }, [currentIndex]);

  const redo = useCallback(() => {
    if (currentIndex < history.length - 1) {
      setCurrentIndex((prev) => prev + 1);
    }
  }, [currentIndex, history.length]);

  const reset = useCallback(() => {
    setHistory([initialState]);
    setCurrentIndex(0);
  }, [initialState]);

  const setParamStateReplace = useCallback((newState: T | ((prevState: T) => T)) => {
    setHistory((prevHistory) => {
      const prev = prevHistory[currentIndex];
      const resolvedState = typeof newState === 'function' ? (newState as ((prevState: T) => T))(prev) : newState;
      const newHistory = [...prevHistory];
      newHistory[currentIndex] = resolvedState;
      return newHistory;
    });
  }, [currentIndex]);

  const canUndo = currentIndex > 0;
  const canRedo = currentIndex < history.length - 1;

  return [state, setParamState, { undo, redo, reset, canUndo, canRedo, setParamStateReplace }] as const;
}
