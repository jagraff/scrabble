# Checkpoint round-trip: end-to-end verification

Not part of the test suite (it takes ~8 minutes and needs the solver); the
suite covers the same logic with synthesised records in 0.48s. Recorded
here because the slow run is the one that exercises the real enumeration
path, and because it is what caught the bug.

Pattern `(0, 2, 3, 7, 11, 13, 14)`, ceiling 1787, PYTHONHASHSEED=0,
one worker.

```
ground truth        : 16 configs, complete=True (274s)
torn checkpoint     : 4 readable   (5 written, final line truncated)
resumed             : 16 from 4, complete=True
RESUMED SET EQUAL   : True   (missing 0, extra 0)
RELOADED SET EQUAL  : True   (16 configs, complete=True)
VERDICT             : PASS
```

The last two lines are the point. Before the fix the resumed run also
returned the right 16 configurations **in memory**, so a test comparing
only the return value passed — while the file on disk held 15 and a
`complete` marker. `RELOADED SET EQUAL` re-reads from disk, which is the
state a later resume would actually see, and it is the check that failed
(15 ≠ 16) and now passes.

Timing note: 274s at one worker against 415s for the same pattern at eight
workers before the fix, and the post-fix model is larger.
