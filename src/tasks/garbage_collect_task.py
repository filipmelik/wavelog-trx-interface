import asyncio
import gc

from helpers.logger import Logger


class GarbageCollectTask:
    
    def __init__(
        self,
        logger: Logger,
    ):
        self._logger = logger
        self._is_running = True
    
    async def run(self):
        while self._is_running:
            self._logger.debug(f"GC task: Mem before GC: {gc.mem_free()}")
            gc.collect()
            self._logger.debug(f"GC task: Mem after GC: {gc.mem_free()}")
            await asyncio.sleep_ms(20000)
            
    def stop(self):
        """
        Stop the running task
        """
        self._is_running = False