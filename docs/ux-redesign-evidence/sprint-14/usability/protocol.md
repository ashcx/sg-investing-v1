# Run the release usability sessions

Recruit five adults who have not used SG / Invest. Use participant codes P1
through P5. Do not collect names, portfolio contents or account details.
Use a stable candidate and record its commit, URL, date, device and browser.
Explain that the product is being evaluated, not the participant. Obtain their
agreement before taking notes or recording. They may stop at any time.

Read each task aloud without describing controls or giving a solution.
Start timing when the participant finishes reading. If they ask for help, ask
what they would try next. Record any actual assistance; an assisted completion
does not count as unaided. Do not promise an investment outcome.

1. Find QQQ. Work out the outcome of a one-time S$10,000 investment for a
   historical period you choose. Explain the actual purchase and valuation
   dates, currency, amount and whether the result matches the current inputs.
2. Model monthly S$500 contributions, first without an initial amount and
   then with an initial S$1,000. Explain total invested, ending value and the
   return measure. Change an input and describe the existing result's status.
3. Compare QQQ and VALL over the same usable period. Explain why their
   available histories differ and which dates the results actually use.
4. Create a fictional portfolio transaction, correct its amount, delete it
   and recover it. Explain where it is saved and how to take a backup.

After each task, ask the participant to identify the displayed currency,
amount, actual period, and whether the result is current or previous. Record
what they actually say. Do not infer comprehension from clicking Calculate.
Record elapsed seconds to the first valid result for task 1, unaided completion
for each task, mistakes, assistance, and the four comprehension observations.
Use null for missing observations. Never substitute an agent simulation.

Copy observations-template.json to a separate anonymized results file. Set
source to real_participant_sessions only after real sessions occurred. Record
candidate_commit, session_date, facilitator and consent_recorded, plus actual
observations. Keep raw personal recordings outside the repository.

Run `python scripts/evaluate_usability.py path/to/results.json`.
The release target requires at least four of five unaided completions for each
task, median time to the first valid result below 60 seconds, and every
participant identifying all four result attributes for each task. A missed
target keeps release acceptance open. Record issues, repair them and run a real
retest. Do not overwrite earlier observations.
