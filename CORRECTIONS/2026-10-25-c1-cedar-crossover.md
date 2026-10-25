Dated correction, 25 October 2026: C1 is met on its printed wording by Cedar LNG, a dated crossover

25 October 2026. As written, C1/O1 is met on the record by Cedar LNG. C1/O1 reads: "PASS: one corridor with two independent financed or offtake signatures, a named FID plus a second financed or offtake signature on the same corridor." On 25 June 2024 the Haisla Nation (50.1 per cent) and Pembina (49.9 per cent) announced a positive final investment decision on Cedar LNG at Kitimat. The same release says Cedar LNG secured a construction term loan with a syndicate of banks, with asset-level debt expected to fund about 60 per cent of the project cost, and holds 20-year take-or-pay tolling agreements with ARC Resources, a third party, and with Pembina, for 1.5 mtpa each. Export Development Canada approved a loan of about C$500 million.

What was wrong: the desk meant a corridor financed after the test was set. It did not write that down. C1/O1 carries no start date and no definition of a corridor. That omission was the desk's error. Public copy then kept saying the corridor test was open, while the desk's own build ledger (data/file-a/build_ledger.py) already marked Cedar LNG "financed_twice: yes".

What happens now: C1/O1 is not edited. The register is append-only and each entry is filled once. C1/O1 keeps its own status (OPEN) and will be scored on 1 January 2027 on its printed wording, which on the record means PASS on Cedar LNG. Cedar LNG reached its decision in 2024, more than two years before C1/O1 was set publicly on 17 September 2026. The result is a dated crossover. It says nothing either way about whether new corridors are being delivered. That question moves to a new entry, C1-C20261025, which follows C1/O1 and does not replace it. It counts only signatures dated on or after 17 September 2026 and defines a corridor in plain words. The narrowing is disclosed in that entry and dated 25 October 2026.

Sources:
Cedar LNG, "Cedar LNG announces positive final investment decision", 25 June 2024: https://www.cedarlng.com/cedar-lng-announces-positive-final-investment-decision/
Canada's National Observer, 26 June 2024, Export Development Canada loan: https://www.nationalobserver.com/2024/06/26/news/export-development-canada-approves-half-billion-haisla-cedar-lng
Date C1/O1 was set publicly: "The face is not the factory", live 17 September 2026, https://barryesharp.substack.com/p/the-face-is-not-the-factory (inventory ledger: LIVE Substack, X and Facebook 17 Sep).

How: C1-C20261025 is added to data/entries.csv with follows_id C1/O1 and blank supersedes columns, so the page does not mark C1/O1 as replaced. No entry in data/entries.csv was edited; the new entry is appended.
