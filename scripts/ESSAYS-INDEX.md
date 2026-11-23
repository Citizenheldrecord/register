# Essay index for the register search box

Barry go t4044u, 23 Nov 2026 05:58 CST, "Go" (GO-0745, AS-279).

The live register Search every column box also lists published Sovereign Realism essays whose text contains the typed word. The page reads `data/essays-index.json`. Rebuild that file after each new public Substack post.

## Rebuild

From this staging repo:

    python3 scripts/build_essays_index.py write --out data/essays-index.json

To add one newly published public essay without waiting on a full refetch, after the post is live:

    python3 scripts/build_essays_index.py write --out data/essays-index.json --no-fetch \
      --add-title "TITLE" --add-date "2026-11-23T12:00:00Z" --add-url "https://barryesharp.substack.com/p/slug" \
      --add-text PATH/TO/CLEAN.txt

Then include `data/essays-index.json` in the essay-links attach upload, or in the next register upload if that manifest is already sealed.

## Publish hook

The attach step is a booked `tools/ship.py` upload of `data/essay-links.csv`. There is no single wrapper to take over mid-publish. After the essay is live, run the write command above and put the new index on the same attach manifest when that is still open. Do not take the ship lock while another publish or upload holds it, and never force-release a lock.

## Tests

    python3 tests/test_essays_index.py

Public posts only. Never-name phrases are removed from the index text and are not printed by the build script.
