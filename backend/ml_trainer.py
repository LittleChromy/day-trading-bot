import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import tensorflow as tf
from tensorflow import keras
import logging
import joblib
import os
from datetime import datetime
from models import db, Trade, Signal, MLModel

logger = logging.getLogger(__name__)

class MLTrainer:
    """
    Machine learning trainer that learns from trading results
    and improves signal accuracy over time
    """
    
    def __init__(self, model_path='model_files/'):
        self.model_path = model_path
        os.makedirs(model_path, exist_ok=True)
        self.scaler = StandardScaler()
    
    def prepare_training_data(self):
        """
        Prepare training data from closed trades and their corresponding signals
        """
        acted_signals = Signal.query.filter(Signal.acted_upon == True).all()
        
        X = []
        y = []
        
        for signal in acted_signals:
            if signal.trade_id:
                trade = Trade.query.get(signal.trade_id)
                if trade and trade.status == 'CLOSED':
                    # Extract features from signal
                    strategy_details = signal.get_strategy_details()
                    features = self._extract_features(strategy_details, signal.confidence_score)
                    
                    # Label: 1 if profitable, 0 if not
                    label = 1 if trade.profit_loss and trade.profit_loss > 0 else 0
                    
                    X.append(features)
                    y.append(label)
        
        if not X:
            logger.warning("No training data available")
            return None, None
        
        X = np.array(X)
        y = np.array(y)
        
        return X, y
    
    def _extract_features(self, strategy_details, confidence):
        """
        Extract feature vector from strategy details
        """
        features = [confidence]
        
        # Extract individual strategy signals and values
        if 'rsi' in strategy_details:
            features.append(strategy_details['rsi']['value'])
            features.append(1 if strategy_details['rsi']['signal'] == 'BUY' else 0)
        
        if 'macd' in strategy_details:
            features.append(strategy_details['macd']['macd'])
            features.append(strategy_details['macd']['histogram'])
        
        if 'bollinger_bands' in strategy_details:
            features.append(strategy_details['bollinger_bands']['upper'])
            features.append(strategy_details['bollinger_bands']['lower'])
        
        if 'moving_average' in strategy_details:
            ma_short = strategy_details['moving_average']['short_ma']
            ma_long = strategy_details['moving_average']['long_ma']
            features.append(ma_short - ma_long)  # Spread
        
        if 'stochastic' in strategy_details:
            features.append(strategy_details['stochastic']['k_percent'])
        
        if 'volume' in strategy_details:
            features.append(strategy_details['volume']['ratio'])
        
        if 'momentum' in strategy_details:
            features.append(strategy_details['momentum']['value'])
        
        # Pad to fixed size if needed
        while len(features) < 12:
            features.append(0)
        
        return features[:12]  # Keep only first 12 features
    
    def train_random_forest(self):
        """
        Train a Random Forest model for signal classification
        """
        X, y = self.prepare_training_data()
        
        if X is None or len(X) < 10:
            logger.warning("Insufficient training data for Random Forest")
            return None
        
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
            
            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # Train model
            model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
            model.fit(X_train_scaled, y_train)
            
            # Evaluate
            accuracy = model.score(X_test_scaled, y_test)
            logger.info(f"Random Forest accuracy: {accuracy:.2%}")
            
            # Save model
            model_filename = f'{self.model_path}random_forest_model.joblib'
            joblib.dump(model, model_filename)
            joblib.dump(self.scaler, f'{self.model_path}scaler.joblib')
            
            # Record in database
            ml_model = MLModel(
                model_name='RandomForest_Signals',
                model_type='Random Forest',
                version=1,
                accuracy=accuracy,
                training_samples=len(X_train),
                is_active=True,
                model_path=model_filename
            )
            db.session.add(ml_model)
            db.session.commit()
            
            return model
        
        except Exception as e:
            logger.error(f"Error training Random Forest: {str(e)}")
            return None
    
    def train_neural_network(self):
        """
        Train a Neural Network for signal classification
        """
        X, y = self.prepare_training_data()
        
        if X is None or len(X) < 20:
            logger.warning("Insufficient training data for Neural Network")
            return None
        
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
            
            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # Build model
            model = keras.Sequential([
                keras.layers.Dense(64, activation='relu', input_shape=(X_train_scaled.shape[1],)),
                keras.layers.Dropout(0.3),
                keras.layers.Dense(32, activation='relu'),
                keras.layers.Dropout(0.3),
                keras.layers.Dense(16, activation='relu'),
                keras.layers.Dense(1, activation='sigmoid')
            ])
            
            model.compile(
                optimizer='adam',
                loss='binary_crossentropy',
                metrics=['accuracy']
            )
            
            # Train
            model.fit(
                X_train_scaled, y_train,
                epochs=50,
                batch_size=8,
                validation_split=0.1,
                verbose=0
            )
            
            # Evaluate
            _, accuracy = model.evaluate(X_test_scaled, y_test, verbose=0)
            logger.info(f"Neural Network accuracy: {accuracy:.2%}")
            
            # Save model
            model_filename = f'{self.model_path}neural_network_model.h5'
            model.save(model_filename)
            joblib.dump(self.scaler, f'{self.model_path}nn_scaler.joblib')
            
            # Record in database
            ml_model = MLModel(
                model_name='NeuralNetwork_Signals',
                model_type='Neural Network',
                version=1,
                accuracy=float(accuracy),
                training_samples=len(X_train),
                is_active=True,
                model_path=model_filename
            )
            db.session.add(ml_model)
            db.session.commit()
            
            return model
        
        except Exception as e:
            logger.error(f"Error training Neural Network: {str(e)}")
            return None

class SignalPredictor:
    """
    Uses trained ML models to predict signal quality and adjust confidence scores
    """
    
    def __init__(self, model_path='model_files/'):
        self.model_path = model_path
        self.rf_model = self._load_random_forest()
        self.nn_model = self._load_neural_network()
        self.rf_scaler = self._load_scaler('scaler.joblib')
        self.nn_scaler = self._load_scaler('nn_scaler.joblib')
    
    def _load_random_forest(self):
        try:
            model_path = f'{self.model_path}random_forest_model.joblib'
            if os.path.exists(model_path):
                return joblib.load(model_path)
        except Exception as e:
            logger.warning(f"Could not load Random Forest model: {str(e)}")
        return None
    
    def _load_neural_network(self):
        try:
            model_path = f'{self.model_path}neural_network_model.h5'
            if os.path.exists(model_path):
                return keras.models.load_model(model_path)
        except Exception as e:
            logger.warning(f"Could not load Neural Network model: {str(e)}")
        return None
    
    def _load_scaler(self, filename):
        try:
            scaler_path = f'{self.model_path}{filename}'
            if os.path.exists(scaler_path):
                return joblib.load(scaler_path)
        except Exception as e:
            logger.warning(f"Could not load scaler: {str(e)}")
        return None
    
    def predict_signal_quality(self, strategy_details, base_confidence):
        """
        Use ML models to predict if a signal will be profitable
        Returns adjusted confidence score
        """
        trainer = MLTrainer()
        features = np.array([trainer._extract_features(strategy_details, base_confidence)])
        
        predictions = []
        
        # Random Forest prediction
        if self.rf_model and self.rf_scaler is not None:
            try:
                features_scaled = self.rf_scaler.transform(features)
                rf_pred = self.rf_model.predict_proba(features_scaled)[0][1]
                predictions.append(rf_pred)
            except Exception as e:
                logger.warning(f"RF prediction error: {str(e)}")
        
        # Neural Network prediction
        if self.nn_model and self.nn_scaler is not None:
            try:
                features_scaled = self.nn_scaler.transform(features)
                nn_pred = float(self.nn_model.predict(features_scaled, verbose=0)[0][0])
                predictions.append(nn_pred)
            except Exception as e:
                logger.warning(f"NN prediction error: {str(e)}")
        
        if predictions:
            # Average ML predictions with base confidence
            ml_average = np.mean(predictions)
            adjusted_confidence = (base_confidence + ml_average) / 2
            return min(adjusted_confidence, 1.0)  # Cap at 1.0
        
        return base_confidence
