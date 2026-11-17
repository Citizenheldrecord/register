import numpy as np
from collections import Counter

np.random.seed(42)
n_sims = 10000

p_us_retaliation = 0.55
p_eu_alliance_success = 0.35
p_europe_hedge_success = 0.40
p_me_stable = 0.65
p_canada_file_close = 0.25
p_us_canada_stabilize = 0.45

us_retaliation = np.random.binomial(1, p_us_retaliation, n_sims)
eu_success = np.random.binomial(1, p_eu_alliance_success, n_sims)
europe_hedge = np.random.binomial(1, p_europe_hedge_success, n_sims)
me_stable = np.random.binomial(1, p_me_stable, n_sims)
canada_files = np.random.binomial(1, p_canada_file_close, n_sims)
us_canada_ok = np.random.binomial(1, p_us_canada_stabilize, n_sims)

canada_score = (
    50
    - 25 * us_retaliation
    + 20 * eu_success
    + 15 * canada_files
    + 10 * us_canada_ok
    + 5 * me_stable
)

europe_score = (
    50
    + 15 * eu_success
    + 20 * europe_hedge
    + 10 * me_stable
    - 15 * us_retaliation
)

def categorize(score):
    if score >= 70:
        return 'Strong resilience / diversification success'
    elif score >= 45:
        return 'Mixed: partial gains, ongoing exposure'
    else:
        return 'High vulnerability / open files dominate'

canada_cats = [categorize(s) for s in canada_score]
europe_cats = [categorize(s) for s in europe_score]

canada_dist = Counter(canada_cats)
europe_dist = Counter(europe_cats)

print("Canada outcome distribution (% of sims):")
for cat, count in canada_dist.most_common():
    print(f"  {cat}: {count/n_sims*100:.1f}%")

print("\nEurope outcome distribution (% of sims):")
for cat, count in europe_dist.most_common():
    print(f"  {cat}: {count/n_sims*100:.1f}%")

print(f"\nMean Canada score: {np.mean(canada_score):.1f}")
print(f"Mean Europe score: {np.mean(europe_score):.1f}")
print(f"P(Canada files close): {np.mean(canada_files):.2f}")
print(f"P(EU alliance delivers): {np.mean(eu_success):.2f}")
