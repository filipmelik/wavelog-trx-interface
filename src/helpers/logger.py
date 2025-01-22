class Logger:
    
    # Log levels
    NO_LOGGING = 50
    EXCEPTION = 30
    INFO = 20
    DEBUG = 10
    
    def __init__(self, log_level: int):
        self._log_level = log_level
        
    def exception(self, message: str):
        if self._log_level <= Logger.EXCEPTION:
            print(f"EXCEPTION: {message}")
        
    def info(self, message: str):
        if self._log_level <= Logger.INFO:
            print(f"INFO: {message}")
    
    def debug(self, message: str):
        if self._log_level <= Logger.DEBUG:
            print(f"DEBUG: {message}")