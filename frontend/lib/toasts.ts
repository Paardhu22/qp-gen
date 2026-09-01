import { toast } from "sonner";

/**
 * An error the teacher can do something about.
 *
 * There were 88 `toast.error` calls in the app and not one carried an
 * `action`. Every failure was a dead end: the toast said what had gone wrong
 * and then took the only obvious next step -- trying again -- and left it to
 * the teacher to work out where it lived. Several were worse than that, asking
 * for an action the toast could perform itself, like "Please refresh."
 *
 * The product already knew how to offer a recovery control. It just only did
 * so when it was about to destroy something -- the delete confirms and the
 * undo on the recycle bin all carry one -- and never when it had failed at
 * something.
 *
 * Use this wherever a retry is genuinely likely to help: a list that did not
 * load, a fetch that timed out. Do not use it where retrying cannot work
 * (validation, a name that is already taken, an empty selection) -- an action
 * that reruns a guaranteed failure is worse than no action, because it implies
 * the failure was transient.
 */
export function errorWithRetry(
  message: string,
  retry: () => void | Promise<unknown>,
): void {
  toast.error(message, {
    action: {
      label: "Retry",
      onClick: () => void retry(),
    },
  });
}
