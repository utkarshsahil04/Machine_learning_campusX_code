# ============================================================
# SOLAR RADIATION PREDICTION PIPELINE
# Dataset columns:
#   Radiation, Temperature, Pressure, Humidity,
#   WindDirection(Degrees), Speed,
#   hour, month, day, weekday, sunrise_hour, sunset_hour
# ============================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split, cross_val_score, RandomizedSearchCV
from sklearn.preprocessing import RobustScaler
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error

from xgboost import XGBRegressor

import warnings
warnings.filterwarnings("ignore")

# ============================================================
# STEP 1 — LOAD DATA
# ============================================================

df = pd.read_csv("your_dataset.csv")   # <-- change to your filename
print("Shape:", df.shape)
print(df.head())


# ============================================================
# STEP 2 — OUTLIER HANDLING (domain-aware)
#
# Radiation   : Physically can't be negative (sensor noise at night).
#               → Clip to 0.
# Humidity    : Must be 0–100 (102 in your data = sensor error).
#               → Clip to valid range.
# Speed       : Can't be negative. Above 100 = likely sensor error.
#               → Clip lower=0, upper=100.
# Temperature : Extreme cold/hot are real weather events. KEEP as-is.
# Pressure    : hPa range 900–1100 covers all real conditions. Cap extremes.
# ============================================================

df["Radiation"] = df["Radiation"].clip(lower=0)
df["Humidity"]  = df["Humidity"].clip(lower=0, upper=100)
df["Speed"]     = df["Speed"].clip(lower=0, upper=100)
df["Pressure"]  = df["Pressure"].clip(lower=900, upper=1100)

print("\nOutlier capping done.")
print("Radiation min:", df["Radiation"].min())   # should be 0 now
print("Humidity  max:", df["Humidity"].max())    # should be ≤ 100 now


# ============================================================
# STEP 3 — FEATURE ENGINEERING
# ============================================================

# --- 3a. Cyclic encoding for hour ---
# WHY: Hour 0 (midnight) and hour 23 are only 1 hour apart,
#      but as raw numbers they look far apart (0 vs 23).
#      Sin/cos wraps hour onto a circle so the model sees
#      them as neighbours.
df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)

# --- 3b. Cyclic encoding for month ---
# WHY: Same reason — December (12) and January (1) are neighbours.
df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

# --- 3c. Daylight duration ---
# WHY: Longer daylight = more hours of possible solar radiation.
#      A single number the model can use directly.
df["daylight_hours"] = df["sunset_hour"] - df["sunrise_hour"]

# --- 3d. Hours since sunrise ---
# WHY: Radiation peaks at solar noon (middle of daylight window),
#      not just at any "daytime" hour.
#      clip(lower=0) → night hours (before sunrise) become 0,
#      meaning "no daylight yet".
df["hour_since_sunrise"] = (df["hour"] - df["sunrise_hour"]).clip(lower=0)

# --- 3e. Temperature / Humidity ratio ---
# WHY: High temp + low humidity = dry clear sky = more radiation.
#      This single ratio captures that interaction.
#      +1 avoids division by zero if Humidity = 0.
df["temp_humidity_ratio"] = df["Temperature"] / (df["Humidity"] + 1)

# --- 3f. Wind × Pressure interaction ---
# WHY: High wind + low pressure often means cloud cover,
#      which reduces radiation. The product captures both together.
df["wind_pressure"] = df["Speed"] * df["Pressure"]


# ============================================================
# STEP 4 — DROP COLUMNS
#
# hour, month       : Replaced by sin/cos versions.
#                     Keeping raw numbers alongside sin/cos
#                     would confuse the model with duplicate info.
# sunrise_hour,
# sunset_hour       : Replaced by daylight_hours and
#                     hour_since_sunrise. Raw values add nothing new.
# ============================================================

df.drop(columns=["hour", "month", "sunrise_hour", "sunset_hour"], inplace=True)

print("\nFinal feature columns:")
print([c for c in df.columns if c != "Radiation"])


# ============================================================
# STEP 5 — CORRELATION HEATMAP
# WHY: Quickly shows which features actually relate to Radiation.
#      Features with near-zero correlation can be dropped later.
# ============================================================

plt.figure(figsize=(13, 9))
sns.heatmap(df.corr(), annot=True, fmt=".2f", cmap="coolwarm", linewidths=0.5)
plt.title("Feature Correlation Heatmap", fontsize=14)
plt.tight_layout()
plt.savefig("correlation_heatmap.png", dpi=150)
plt.show()
print("Heatmap saved → correlation_heatmap.png")


# ============================================================
# STEP 6 — SPLIT FEATURES AND TARGET
# ============================================================

TARGET   = "Radiation"
FEATURES = [col for col in df.columns if col != TARGET]

X = df[FEATURES]
y = df[TARGET]

print(f"\nTotal features: {len(FEATURES)}")
print("Features:", FEATURES)


# ============================================================
# STEP 7 — TRAIN / TEST SPLIT
# 80% train, 20% test.
# random_state=42 → same split every time you run the code.
# ============================================================

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)
print(f"\nTrain: {X_train.shape}  |  Test: {X_test.shape}")


# ============================================================
# STEP 8 — SCALING (only needed for Linear Regression)
#
# WHY RobustScaler:
#   StandardScaler → uses mean + std → outliers drag it off
#   MinMaxScaler   → uses min/max   → one extreme value ruins the scale
#   RobustScaler   → uses median + IQR → outliers have no effect
#
# WHY fit only on X_train:
#   If you fit on the full dataset, test data "leaks" into the scaler.
#   Your RMSE will look better than it really is.
#   Always fit on train, transform both train and test.
# ============================================================

scaler = RobustScaler()
X_train_scaled = scaler.fit_transform(X_train)   # fit + transform train
X_test_scaled  = scaler.transform(X_test)         # transform only (no fit)


# ============================================================
# STEP 9 — EVALUATE HELPER FUNCTION
# ============================================================

def evaluate(name, model, X_tr, y_tr, X_te, y_te):
    """Train model, print Test RMSE and 5-fold CV RMSE."""
    model.fit(X_tr, y_tr)
    preds = model.predict(X_te)
    rmse  = np.sqrt(mean_squared_error(y_te, preds))

    cv    = cross_val_score(model, X_tr, y_tr,
                             scoring="neg_root_mean_squared_error", cv=5)
    cv_rmse = -cv.mean()

    print(f"\n{'─'*45}")
    print(f"  Model     : {name}")
    print(f"  Test RMSE : {rmse:.4f}")
    print(f"  CV RMSE   : {cv_rmse:.4f}  (5-fold average)")
    return rmse, preds


results = {}


# ============================================================
# STEP 10 — MODEL 1: LINEAR REGRESSION  (Baseline)
#
# WHY start here:
#   Simplest model. If Random Forest barely beats it,
#   your features are doing most of the heavy lifting already.
#   Uses SCALED data because LR is sensitive to feature scale.
# ============================================================

rmse_lr, preds_lr = evaluate(
    "Linear Regression",
    LinearRegression(),
    X_train_scaled, y_train,
    X_test_scaled,  y_test
)
results["Linear Regression"] = rmse_lr


# ============================================================
# STEP 11 — MODEL 2: RANDOM FOREST
#
# WHY:
#   Builds many decision trees and averages their predictions.
#   Each tree uses a random subset of features and rows
#   → diverse trees → less overfitting → better generalisation.
#   Tree splits are rank-based, so outliers don't affect it.
#   Does NOT need scaled data.
# ============================================================

rf = RandomForestRegressor(
    n_estimators   = 200,    # 200 trees — good speed/accuracy balance
    max_depth      = 15,     # limits tree depth → avoids memorising train data
    min_samples_leaf = 4,    # leaf needs ≥4 samples → smoother predictions
    n_jobs         = -1,     # use all CPU cores
    random_state   = 42
)

rmse_rf, preds_rf = evaluate(
    "Random Forest",
    rf,
    X_train, y_train,   # unscaled — trees don't need scaling
    X_test,  y_test
)
results["Random Forest"] = rmse_rf


# ============================================================
# STEP 12 — MODEL 3: XGBOOST
#
# WHY:
#   Builds trees sequentially. Each new tree learns from the
#   errors of all previous trees (gradient boosting).
#   Usually the best RMSE on tabular / weather datasets.
#   Does NOT need scaled data.
#
# Key params explained:
#   learning_rate  : How much each tree corrects. Small = slower
#                    but more accurate (pair with more n_estimators).
#   subsample      : Each tree uses 80% of rows → prevents overfit.
#   colsample_bytree: Each tree uses 80% of features → more diversity.
#   reg_alpha/lambda: L1/L2 regularisation → punishes complexity.
# ============================================================

xgb = XGBRegressor(
    n_estimators     = 500,
    learning_rate    = 0.05,
    max_depth        = 6,
    subsample        = 0.8,
    colsample_bytree = 0.8,
    reg_alpha        = 0.1,
    reg_lambda       = 1.0,
    n_jobs           = -1,
    random_state     = 42,
    verbosity        = 0
)

rmse_xgb, preds_xgb = evaluate(
    "XGBoost",
    xgb,
    X_train, y_train,
    X_test,  y_test
)
results["XGBoost"] = rmse_xgb


# ============================================================
# STEP 13 — HYPERPARAMETER TUNING (XGBoost)
#
# WHY RandomizedSearchCV over GridSearchCV:
#   Grid   = tries every single combination (too slow).
#   Random = tries N random combinations → finds good params fast.
#   n_iter=30 → 30 random combos, each with 5-fold CV = 150 fits.
#   Usually finds 90% of the best result in 10% of the time.
# ============================================================

print("\n⏳  Tuning XGBoost with RandomizedSearchCV...")
print("    (30 random combos × 5-fold CV = 150 fits. Takes ~2–5 min)")

param_grid = {
    "n_estimators"     : [300, 500, 700],
    "max_depth"        : [4, 6, 8],
    "learning_rate"    : [0.01, 0.05, 0.1],
    "subsample"        : [0.7, 0.8, 0.9],
    "colsample_bytree" : [0.7, 0.8, 0.9],
    "reg_alpha"        : [0, 0.1, 0.5],
    "reg_lambda"       : [0.5, 1.0, 2.0],
}

search = RandomizedSearchCV(
    XGBRegressor(random_state=42, verbosity=0, n_jobs=-1),
    param_distributions = param_grid,
    n_iter              = 30,
    scoring             = "neg_root_mean_squared_error",
    cv                  = 5,
    random_state        = 42,
    n_jobs              = -1
)
search.fit(X_train, y_train)

best_xgb   = search.best_estimator_
preds_best = best_xgb.predict(X_test)
rmse_best  = np.sqrt(mean_squared_error(y_test, preds_best))

print(f"\n  Best XGBoost (tuned) RMSE : {rmse_best:.4f}")
print(f"  Best params found        :")
for k, v in search.best_params_.items():
    print(f"      {k}: {v}")

results["XGBoost (Tuned)"] = rmse_best


# ============================================================
# STEP 14 — FINAL COMPARISON TABLE
# ============================================================

print("\n" + "="*50)
print("         FINAL MODEL COMPARISON")
print("="*50)
for name, rmse in sorted(results.items(), key=lambda x: x[1]):
    marker = "  ← BEST" if rmse == min(results.values()) else ""
    print(f"  {name:<25}  RMSE = {rmse:.4f}{marker}")
print("="*50)

best_name = min(results, key=results.get)
print(f"\n🏆  Best model : {best_name}")
print(f"    Final RMSE : {results[best_name]:.4f}")


# ============================================================
# STEP 15 — FEATURE IMPORTANCE (XGBoost Tuned)
#
# WHY check this:
#   Features with near-zero importance can be dropped.
#   Removing them = faster model, sometimes better RMSE.
# ============================================================

feat_imp = pd.Series(
    best_xgb.feature_importances_,
    index=FEATURES
).sort_values(ascending=False)

plt.figure(figsize=(10, 6))
feat_imp.plot(kind="bar", color="steelblue", edgecolor="white")
plt.title("XGBoost Feature Importance", fontsize=13)
plt.ylabel("Importance Score")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.savefig("feature_importance.png", dpi=150)
plt.show()

print("\nTop 5 most important features:")
print(feat_imp.head(5).to_string())


# ============================================================
# STEP 16 — ACTUAL vs PREDICTED PLOT
# ============================================================

plt.figure(figsize=(7, 6))
plt.scatter(y_test, preds_best, alpha=0.4, color="steelblue", s=12, label="Predictions")
plt.plot([y_test.min(), y_test.max()],
         [y_test.min(), y_test.max()],
         "r--", lw=2, label="Perfect prediction line")
plt.xlabel("Actual Radiation")
plt.ylabel("Predicted Radiation")
plt.title(f"Actual vs Predicted  |  RMSE = {rmse_best:.4f}")
plt.legend()
plt.tight_layout()
plt.savefig("actual_vs_predicted.png", dpi=150)
plt.show()

print("\n✅  Pipeline complete. Files saved:")
print("    → correlation_heatmap.png")
print("    → feature_importance.png")
print("    → actual_vs_predicted.png")