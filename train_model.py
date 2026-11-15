"""
ASTRA CARE 2.0 - Standalone Model Training Runner
Execute with: python train_model.py
"""
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.ml.train import train_and_evaluate_model

if __name__ == "__main__":
    train_and_evaluate_model()
