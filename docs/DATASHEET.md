# Datasheet

## Motivation
A bank must keep checkout moving during a flash sale and still stop a bot ring that hides in the same spike. The dataset is two days of card transactions, already reduced by PCA.

## Composition
- Training file: 199,364 rows, 344 fraud (0.17%) including 591 exact duplicate rows.
- After duplicates are dropped: 198,773 training rows and 332 fraud.
- Test file: 42,720 rows, 73 fraud, of which 29 are exact duplicates. After drop: 42,691 rows and 72 fraud.
- `Time` spans 0 to 172,792 seconds (48 hours) in both files. The test file is a held-out sample of the same window, not the next month.
- `Amount` median is about 22 for legitimate payments and about 9 for fraud. Fraud is not the large payments.
- Fraud rate around 02:00 is about 1.8%, against about 0.1% in the day.

## Collection
Provided by the organisers. Participants do not know the original issuer, the country, or the PCA loadings. That is treated as a privacy property, not a bug to be reversed.

## Preprocessing
- Drop exact duplicate rows (591 in train, 29 in test).
- `log(1 + amount)`, hour-of-day, overnight flag.
- Causal counts and amount moments over 10 seconds, 60 seconds, and 5 minutes.
- Up to 8-means clusters in V-space, fit on the training slice only. Amount z-score and distance to the segment centroid use training statistics.
- No SMOTE. The champion uses `class_weight="balanced"` on logistic regression. LightGBM is the shadow model and is trained without a huge `scale_pos_weight`, because that setting hurt ranking on this PCA file.

## Recommended use
- Ranking and a three-way checkout decision on this schema.
- Not for credit decisioning, not for marketing, not for inferring the identity behind a PCA component.

## Maintenance
- PSI against the training score histogram. Alert at 0.2.
- Retrain when the alert stays on, or on a schedule. The artifact records seed, file hashes, and timestamp.
