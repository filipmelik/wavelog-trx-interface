from lib import ssd1306


class DisplayHelper:
    """
    Wrapper around OLED display library to simplify some of the display tasks
    """
    PIXELS_PER_TEXT_LINE = 12
    
    def __init__(self, oled_display: ssd1306.SSD1306_I2C):
        self._oled_display = oled_display
        
    def display_text(self, text_lines: list):
        """
        Display given text rows list on the display
        """
        if not text_lines:
            return
        
        self._oled_display.fill(0)  # clear display
        for row_index, row_text in enumerate(text_lines):
            self._oled_display.text(
                row_text,
                0,
                row_index * self.PIXELS_PER_TEXT_LINE,
                1,
            )
        self._oled_display.show() # send buffered data on screen
        