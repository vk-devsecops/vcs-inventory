import json
import logging

from settings.config import LOG_LEVEL, ENVIRONMENT


class JsonFormatter(logging.Formatter):
    def format(self, record):
        basic_record_keys = (
            "name", "args", "levelno", "filename", "module", "exc_info", "exc_text", "stack_info", "created", "msecs",
            "relativeCreated", "thread", "threadName", "processName", "process", "levelname", "msg", "pathname",
            "lineno", "funcName"
        )
        log_data = {
            "timestamp": self.formatTime(record),
            "log_level": record.levelname,
            "msg": record.msg,
            "funcName": record.funcName,
            "pathname": record.pathname,
            "lineno": record.lineno
        }
        for key, value in record.__dict__.items():
            if key not in basic_record_keys:
                log_data[key] = value
        log_data.pop("vars") if log_data.get("vars") and record.levelname.lower() == 'info' else None
        return json.dumps(log_data, default=str)


logger = logging.getLogger()
logging.getLogger('urllib3').setLevel(logging.ERROR)

if LOG_LEVEL:
    logger.setLevel(LOG_LEVEL)
else:
    logger.setLevel(logging.INFO)

if ENVIRONMENT and ENVIRONMENT == "DEV":
    basic_handler = logging.StreamHandler()
    time_format = "%Y-%m-%d %H:%M:%S"
    basic_handler.setFormatter(
        logging.Formatter(fmt='[%(asctime)s] [%(levelname)s] <%(module)s> - %(funcName)s: %(message)s',
                          datefmt=time_format))
    logger.addHandler(basic_handler)
else:
    json_handler = logging.StreamHandler()
    json_handler.setFormatter(JsonFormatter())
    logger.addHandler(json_handler)
