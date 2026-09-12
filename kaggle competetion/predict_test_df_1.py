import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor


TRAIN_FILE = "train_df_1.csv"
TEST_FILE = "test_df_1.csv"
OUTPUT_FILE = "test_df_1_predictions.csv"
TARGET = "Radiation"


def add_time_features(df):
    """Convert the raw Kaggle date/time columns into model-ready fields."""
    result = df.copy()

    dates = pd.to_datetime(result["Data"], format="%d-%m-%Y", errors="coerce")
    times = pd.to_datetime(result["Time"], format="%H:%M:%S", errors="coerce")

    result["hour"] = times.dt.hour
    result["month"] = dates.dt.month
    result["day"] = dates.dt.day
    result["weekday"] = dates.dt.weekday
    result["sunrise_hour"] = result["TimeSunRise"].str.split(":").str[0].astype(float)
    result["sunset_hour"] = result["TimeSunSet"].str.split(":").str[0].astype(float)

    return result


def engineer_features(df, medians):
    result = add_time_features(df)

    numeric_columns = [
        "Temperature",
        "Pressure",
        "Humidity",
        "WindDirection(Degrees)",
        "Speed",
        "hour",
        "month",
        "day",
        "weekday",
        "sunrise_hour",
        "sunset_hour",
    ]

    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
        result[column] = result[column].fillna(medians[column])

    if TARGET in result.columns:
        result[TARGET] = pd.to_numeric(result[TARGET], errors="coerce").clip(lower=0)

    result["Humidity"] = result["Humidity"].clip(lower=0, upper=100)
    result["Speed"] = result["Speed"].clip(lower=0, upper=100)
    result["Pressure"] = result["Pressure"].clip(lower=900, upper=1100)

    result["hour_sin"] = np.sin(2 * np.pi * result["hour"] / 24)
    result["hour_cos"] = np.cos(2 * np.pi * result["hour"] / 24)
    result["month_sin"] = np.sin(2 * np.pi * result["month"] / 12)
    result["month_cos"] = np.cos(2 * np.pi * result["month"] / 12)
    result["daylight_hours"] = result["sunset_hour"] - result["sunrise_hour"]
    result["hour_since_sunrise"] = (result["hour"] - result["sunrise_hour"]).clip(lower=0)
    result["temp_humidity_ratio"] = result["Temperature"] / (result["Humidity"] + 1)
    result["wind_pressure"] = result["Speed"] * result["Pressure"]

    return result.drop(
        columns=[
            "ID",
            "UNIXTime",
            "Data",
            "Time",
            "TimeSunRise",
            "TimeSunSet",
            "hour",
            "month",
            "sunrise_hour",
            "sunset_hour",
        ],
        errors="ignore",
    )


def main():
    train_raw = pd.read_csv(TRAIN_FILE)
    test_raw = pd.read_csv(TEST_FILE)

    train_with_time = add_time_features(train_raw)
    median_columns = [
        "Temperature",
        "Pressure",
        "Humidity",
        "WindDirection(Degrees)",
        "Speed",
        "hour",
        "month",
        "day",
        "weekday",
        "sunrise_hour",
        "sunset_hour",
    ]
    medians = train_with_time[median_columns].median(numeric_only=True)

    train_ready = engineer_features(train_raw, medians)
    test_ready = engineer_features(test_raw, medians)

    feature_columns = [column for column in train_ready.columns if column != TARGET]
    X_train = train_ready[feature_columns]
    y_train = train_ready[TARGET]
    X_test = test_ready[feature_columns]

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=15,
        min_samples_leaf=4,
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X_train, y_train)

    output = test_raw.copy()
    output["PredictedRadiation"] = model.predict(X_test)
    output.to_csv(OUTPUT_FILE, index=False)

    print(f"Saved {len(output)} rows to {OUTPUT_FILE}")
    print(output[["ID", "PredictedRadiation"]].head().to_string(index=False))


if __name__ == "__main__":
    main()
