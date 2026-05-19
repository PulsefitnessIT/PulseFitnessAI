/* eslint-env jest */

import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import { useBackGestureClose } from './useBackGestureClose';

// Tiny harness component — exposes the hook as a render-side-effect.
const Harness = ({ open, onClose, k }) => {
  useBackGestureClose(open, onClose, k);
  return null;
};

describe('iter 216f — useBackGestureClose', () => {
  let pushStateSpy;
  let backSpy;
  let container;
  let root;

  beforeEach(() => {
    pushStateSpy = jest.spyOn(window.history, 'pushState');
    backSpy = jest.spyOn(window.history, 'back').mockImplementation(() => {});
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => { root.unmount(); });
    container.remove();
    pushStateSpy.mockRestore();
    backSpy.mockRestore();
  });

  test('pushes a phantom history entry when open=true', () => {
    act(() => {
      root.render(<Harness open onClose={jest.fn()} k="test-modal" />);
    });
    expect(pushStateSpy).toHaveBeenCalledTimes(1);
    expect(pushStateSpy.mock.calls[0][0]).toEqual({ 'test-modal': true });
  });

  test('does NOT push when open=false', () => {
    act(() => {
      root.render(<Harness open={false} onClose={jest.fn()} k="test-modal" />);
    });
    expect(pushStateSpy).not.toHaveBeenCalled();
  });

  test('popstate triggers onClose', () => {
    const onClose = jest.fn();
    act(() => {
      root.render(<Harness open onClose={onClose} k="test-modal" />);
    });
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test('clean unmount (no popstate) calls history.back() once', () => {
    // Pre-set the phantom marker so the cleanup branch fires.
    window.history.replaceState({ 'test-modal': true }, '');
    const onClose = jest.fn();
    act(() => {
      root.render(<Harness open onClose={onClose} k="test-modal" />);
    });
    act(() => { root.unmount(); });
    // Re-create root for afterEach.
    root = createRoot(container);

    expect(backSpy).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  test('popstate-driven close skips the cleanup history.back() (no double back)', () => {
    window.history.replaceState({ 'test-modal': true }, '');
    const onClose = jest.fn();
    act(() => {
      root.render(<Harness open onClose={onClose} k="test-modal" />);
    });
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    act(() => { root.unmount(); });
    root = createRoot(container);

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(backSpy).not.toHaveBeenCalled();
  });

  test('different keys keep stacked modals isolated', () => {
    const closeA = jest.fn();
    const closeB = jest.fn();
    act(() => {
      root.render(
        <>
          <Harness open onClose={closeA} k="modal-a" />
          <Harness open onClose={closeB} k="modal-b" />
        </>
      );
    });
    expect(pushStateSpy).toHaveBeenCalledTimes(2);
    expect(pushStateSpy.mock.calls[0][0]).toEqual({ 'modal-a': true });
    expect(pushStateSpy.mock.calls[1][0]).toEqual({ 'modal-b': true });
  });
});
