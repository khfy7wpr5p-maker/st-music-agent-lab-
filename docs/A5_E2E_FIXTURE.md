# A5 real bounded fixture

A real repository fixture is used to validate the A5 task-branch shape without merging it.

- implementation branch: `a5/lab-only-pr-writer`
- fixture branch: `agent/a5-fixture-green-pr`
- allowed fixture path: `fixtures/a5/`
- merge authority: disabled
- production/cross-repository authority: disabled

The fixture PR must run the same `foundation` Python 3.12 unit suite and become green before A5 is considered complete.
