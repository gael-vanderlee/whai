# close-session

OK, let's close this session.
Review everything that we have done so far, and take note of what is important.
Now let's close the session by:
1. Run all tests. If some tests fail, identify why: is the code not working properly ? Fix the code. Is the test broken ? Fix the test. Is the test not relevant anymore ? Remove the test.
2. Update the changelog (see instructions below)
3. Check all the project documentation and update it accordingly (see instructions below)
4. Look at all the uncommited changes. Group them semantically (no need to commit each file one by one) and commit each semantic change individually, with appropriate but short (<10 words) messages


## Changelog
First, start by running a command in the terminal to get the current date and time. Your percieved date and time is wrong, don't trust it, get the system time.
Once a feature has been implemented or a bug has been confirmed fixed, update the CHANGELOG.md file in order to document what's been done, and when. Keep it concise, but make sure it contains the important information (what core of the issue was, what decision was taken, how the fix was implemented).
Respect the CHANGELOG guidelines outlined in the file.

## Other documentation
Check all other documentation in the project, and check for:
1. Changes are made to the files that makes the documentation obsolete or incomplete
2. If the code and the documentation are not aligned (contradictions, incomplete information etc)
In those cases, update the documentation accordingly.

