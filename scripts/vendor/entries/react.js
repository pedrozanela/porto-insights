// "react" para o import map. O React 18 é CommonJS: os nomes precisam ser re-exportados um a um.
import React from "react";

export default React;
export const {
  Children, Component, Fragment, Profiler, PureComponent, StrictMode, Suspense,
  cloneElement, createContext, createElement, createRef, forwardRef, isValidElement, lazy, memo,
  startTransition, useCallback, useContext, useDebugValue, useDeferredValue, useEffect, useId,
  useImperativeHandle, useInsertionEffect, useLayoutEffect, useMemo, useReducer, useRef, useState,
  useSyncExternalStore, useTransition, version,
} = React;
