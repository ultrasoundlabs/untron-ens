import json
import logging.config
import os
import datetime
from typing import Dict, Any
from pathlib import Path

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# Constants
DB_FILENAME = str(PROJECT_ROOT / "receivers.db")

# Load configuration from JSON
def load_config() -> Dict[str, Any]:
    with open(PROJECT_ROOT / "config.json") as f:
        return json.load(f)

# Load ABIs
def load_abis() -> Dict[str, Any]:
    FACTORY_ABI = json.load(open(PROJECT_ROOT / "out/ReceiverFactory.json"))["abi"]
    RECEIVER_ABI = json.load(open(PROJECT_ROOT / "out/UntronReceiver.json"))["abi"]
    ERC20_ABI = [
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "name": "from", "type": "address"},
                {"indexed": True, "name": "to", "type": "address"},
                {"indexed": False, "name": "value", "type": "uint256"}
            ],
            "name": "Transfer",
            "type": "event"
        }
    ]
    return {
        "factory": FACTORY_ABI,
        "receiver": RECEIVER_ABI,
        "erc20": ERC20_ABI
    }

def setup_logging() -> None:
    os.makedirs(PROJECT_ROOT / "logs", exist_ok=True)
    
    LOGGING_CONFIG = {
        "version": 1,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
        },
        "handlers": {
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(PROJECT_ROOT / "logs" / "relayer.log"),
                "maxBytes": 10*1024*1024,  # 10MB
                "backupCount": 5,
                "formatter": "default",
            },
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default"
            }
        },
        "root": {
            "handlers": ["file", "console"],
            "level": "INFO",
        },
    }
    
    logging.config.dictConfig(LOGGING_CONFIG)

# Initialize configuration
CONFIG = load_config()
ABIS = load_abis()
setup_logging()

# Create logger for this module
logger = logging.getLogger(__name__)
