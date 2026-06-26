# ADR 0016: Same-Close Execution Prohibited

An order that uses closing data from date D may not execute at that same close. The default EOD-safe path is decision after data availability, then execution at the next eligible session open.
