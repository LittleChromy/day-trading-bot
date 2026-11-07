"""
Self-learning layer: learns which signals turned into profitable trades and
uses that to adjust the confidence of new signals.

TensorFlow is optional. If it is not installed the neural network is skipped
and only the Random Forest is used.
"""
import logging
import os
from datetime import datetime

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from config import Config
from models import db, Trade, Signal, MLModel

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    'confidence', 'side', 'rsi', 'macd_hist_pct', 'bb_percent_b',
    'ma_spread_pct', 'stoch_k', 'volume_ratio', 'momentum', 'agreeing_strategies',
]
MIN_SAMPLES_RF = 10
MIN_SAMPLES_NN = 30


def _keras():
    try:
        from tensorflow import keras  # noqa: WPS433 (optional heavy import)
        return keras
    except Exception:
        return None


def extract_features(strategy_details, confidence, signal_type='BUY', price=None):
    """
    Fixed-length feature vector. Every feature has its own slot with a neutral
    default, so a missing strategy never shifts the other columns.
    """
    d = strategy_details or {}

    def val(strategy, key, default):
        v = d.get(strategy, {}).get(key)
        return default if v is None else float(v)

    side = 1.0 if signal_type == 'BUY' else -1.0
    rsi = val('rsi', 'value', 50.0)

    hist = val('macd', 'histogram', 0.0)
    macd_hist_pct = hist / price * 100 if price else hist

    upper, lower = val('bollinger_bands', 'upper', 0.0), val('bollinger_bands', 'lower', 0.0)
    if price and upper > lower:
        bb_b = (price - lower) / (upper - lower)
    else:
        bb_b = 0.5

    short_ma, long_ma = val('moving_average', 'short_ma', 0.0), val('moving_average', 'long_ma', 0.0)
    ma_spread = (short_ma - long_ma) / long_ma * 100 if long_ma else 0.0

    agreeing = sum(1 for s in d.values() if isinstance(s, dict) and s.get('signal') == signal_type)

    return [
        float(confidence or 0.0), side, rsi, macd_hist_pct, bb_b, ma_spread,
        val('stochastic', 'k_percent', 50.0), val('volume', 'ratio', 1.0),
        val('momentum', 'value', 0.0), float(agreeing),
    ]


class MLTrainer:
    """Trains models on closed trades that originated from signals"""

    def __init__(self, model_path=None):
        self.model_path = model_path or Config.MODEL_PATH
        os.makedirs(self.model_path, exist_ok=True)

    def _path(self, filename):
        return os.path.join(self.model_path, filename)

    def prepare_training_data(self):
        rows = (db.session.query(Signal, Trade)
                .join(Trade, Signal.trade_id == Trade.id)
                .filter(Signal.acted_upon.is_(True), Trade.status == 'CLOSED')
                .all())
        X, y = [], []
        for signal, trade in rows:
            X.append(extract_features(signal.get_strategy_details(), signal.base_confidence or signal.confidence_score,
                                      signal.signal_type, signal.current_price))
            y.append(1 if (trade.profit_loss or 0) > 0 else 0)
        if not X:
            logger.info("No training data available yet")
            return None, None
        return np.array(X, dtype=float), np.array(y, dtype=int)

    def _next_version(self, name):
        latest = MLModel.query.filter_by(model_name=name).order_by(MLModel.version.desc()).first()
        return (latest.version + 1) if latest else 1

    def _record(self, name, model_type, accuracy, samples, path):
        MLModel.query.filter_by(model_name=name, is_active=True).update({'is_active': False})
        db.session.add(MLModel(
            model_name=name, model_type=model_type, version=self._next_version(name),
            accuracy=float(accuracy), training_samples=int(samples), is_active=True,
            model_path=path, last_retrained=datetime.utcnow(),
        ))
        db.session.commit()

    @staticmethod
    def _split(X, y):
        # Stratify only when both classes have enough members
        stratify = y if len(set(y)) > 1 and min(np.bincount(y)) >= 2 else None
        return train_test_split(X, y, test_size=0.2, random_state=42, stratify=stratify)

    def train_random_forest(self):
        X, y = self.prepare_training_data()
        if X is None or len(X) < MIN_SAMPLES_RF:
            logger.info("Insufficient training data for Random Forest")
            return None
        if len(set(y)) < 2:
            logger.info("Training data has only one outcome class; skipping Random Forest")
            return None
        try:
            X_train, X_test, y_train, y_test = self._split(X, y)
            scaler = StandardScaler()
            X_train_s = scaler.fit_transform(X_train)
            X_test_s = scaler.transform(X_test)

            model = RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=2,
                                           class_weight='balanced', random_state=42)
            model.fit(X_train_s, y_train)
            accuracy = model.score(X_test_s, y_test)
            logger.info(f"Random Forest accuracy: {accuracy:.2%} on {len(X_test)} held-out trades")

            path = self._path('random_forest_model.joblib')
            joblib.dump(model, path)
            joblib.dump(scaler, self._path('scaler.joblib'))
            self._record('RandomForest_Signals', 'Random Forest', accuracy, len(X_train), path)
            return model
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error training Random Forest: {e}")
            return None

    def train_neural_network(self):
        keras = _keras()
        if keras is None:
            logger.info("TensorFlow not installed; skipping neural network")
            return None
        X, y = self.prepare_training_data()
        if X is None or len(X) < MIN_SAMPLES_NN or len(set(y)) < 2:
            logger.info("Insufficient training data for Neural Network")
            return None
        try:
            X_train, X_test, y_train, y_test = self._split(X, y)
            scaler = StandardScaler()
            X_train_s = scaler.fit_transform(X_train)
            X_test_s = scaler.transform(X_test)

            model = keras.Sequential([
                keras.layers.Input(shape=(X_train_s.shape[1],)),
                keras.layers.Dense(32, activation='relu'),
                keras.layers.Dropout(0.3),
                keras.layers.Dense(16, activation='relu'),
                keras.layers.Dense(1, activation='sigmoid'),
            ])
            model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
            model.fit(X_train_s, y_train, epochs=50, batch_size=8, validation_split=0.1, verbose=0,
                      callbacks=[keras.callbacks.EarlyStopping(patience=5, restore_best_weights=True)])
            _, accuracy = model.evaluate(X_test_s, y_test, verbose=0)
            logger.info(f"Neural Network accuracy: {accuracy:.2%}")

            path = self._path('neural_network_model.keras')
            model.save(path)
            joblib.dump(scaler, self._path('nn_scaler.joblib'))
            self._record('NeuralNetwork_Signals', 'Neural Network', accuracy, len(X_train), path)
            return model
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error training Neural Network: {e}")
            return None

    def train_all(self):
        return {
            'random_forest': self.train_random_forest() is not None,
            'neural_network': self.train_neural_network() is not None,
        }


class SignalPredictor:
    """Uses trained models to predict signal quality and adjust confidence"""

    def __init__(self, model_path=None):
        self.model_path = model_path or Config.MODEL_PATH
        self.reload()

    def _load(self, filename, loader=joblib.load):
        path = os.path.join(self.model_path, filename)
        try:
            if os.path.exists(path):
                return loader(path)
        except Exception as e:
            logger.warning(f"Could not load {filename}: {e}")
        return None

    def reload(self):
        self.rf_model = self._load('random_forest_model.joblib')
        self.rf_scaler = self._load('scaler.joblib')
        keras = _keras()
        self.nn_model = self._load('neural_network_model.keras', keras.models.load_model) if keras else None
        self.nn_scaler = self._load('nn_scaler.joblib')

    @property
    def has_models(self):
        return bool((self.rf_model is not None and self.rf_scaler is not None)
                    or (self.nn_model is not None and self.nn_scaler is not None))

    def predict_signal_quality(self, strategy_details, base_confidence, signal_type='BUY', price=None):
        """Returns the confidence blended with the models' win probability"""
        features = np.array([extract_features(strategy_details, base_confidence, signal_type, price)])
        predictions = []

        if self.rf_model is not None and self.rf_scaler is not None:
            try:
                predictions.append(float(self.rf_model.predict_proba(self.rf_scaler.transform(features))[0][1]))
            except Exception as e:
                logger.warning(f"RF prediction error: {e}")

        if self.nn_model is not None and self.nn_scaler is not None:
            try:
                predictions.append(float(self.nn_model.predict(self.nn_scaler.transform(features), verbose=0)[0][0]))
            except Exception as e:
                logger.warning(f"NN prediction error: {e}")

        if not predictions:
            return base_confidence
        return float(min(max((base_confidence + float(np.mean(predictions))) / 2, 0.0), 1.0))
