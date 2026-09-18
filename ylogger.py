"""
УНИВЕРСАЛЬНЫЙ ЛОГГЕР (ylogger) v1.1

● НАЗНАЧЕНИЕ:
  Модуль для настройки логирования в Python-приложениях с:
  - Записью в файл и выводом в консоль
  - Поддержкой эмодзи
  - Очисткой старых логов
  - Автоматической кодировкой UTF-8 для русского языка

● КАК ИСПОЛЬЗОВАТЬ:
  from ylogger import ylog
  
  logger = ylog(
      logger_name=__name__,
      log_dir="мои_логи",
      file_level="DEBUG",
      max_log_age=30   # удалять логи старше 30 дней
  )
  
  logger.info("Программа запущена!")

● ПАРАМЕТРЫ:
  logger_name   : Имя вашего приложения (лучше использовать __name__)
  log_dir       : Папка для логов (по умолчанию 'logs')
  log_filename  : Фиксированное имя файла (если не нужно авто)
  file_level    : Детализация для файла (DEBUG/INFO/WARNING/ERROR)
  console_level : Детализация для консоли (по умолчанию INFO)
  use_emoji     : Эмодзи в консоли (True/False)
  formatter     : Стиль сообщений ('basic', 'detailed', 'raw')
  max_log_age   : Удалять логи старше N дней (0=отключить)
  use_console   : Вывод в консоль (True/False)
  use_file      : Запись в файл (True/False)

● ПРИМЕРЫ СООБЩЕНИЙ:
  С эмодзи:  [ℹ️ INFO] Программа запущена
  Без эмодзи: [INFO] Программа запущена

● ОЧИСТКА ЛОГОВ:
  Удаляются ТОЛЬКО файлы текущего приложения в формате:
  [logger_name]_*.log (например: main_20240101.log)

● КОДИРОВКА:
  Всегда используется utf-8-sig для правильного отображения русского
  в любых терминалах и редакторах.
"""
import logging
import os
import sys
import glob
import time
from datetime import datetime

# ЭМОДЗИ ДЛЯ РАЗНЫХ УРОВНЕЙ ВАЖНОСТИ
EMOJI_MAP = {
    "DEBUG": "🐛 ",    # Жук для отладочных сообщений
    "INFO": "ℹ️ ",     # Информационный знак
    "WARNING": "⚠️ ",  # Предупреждающий знак
    "ERROR": "❌ ",    # Красный крестик
    "CRITICAL": "💥 "  # Взрыв для критических ошибок
}

class EmojiFormatter(logging.Formatter):
    """Добавляет эмодзи к уровню логирования"""
    def format(self, record):
        # Добавляем эмодзи перед уровнем важности
        if record.levelname in EMOJI_MAP:
            record.levelname = EMOJI_MAP[record.levelname] + record.levelname
        return super().format(record)

def ylog(
    logger_name: str,
    log_dir: str = "logs",
    log_filename: str = None,
    file_level: str = "DEBUG",
    console_level: str = "INFO",
    use_emoji: bool = True,
    formatter: str = "detailed",
    max_log_age: int = 0,
    use_console: bool = True,
    use_file: bool = True,
) -> logging.Logger:
    """
    Настройка системы логирования для вашего приложения
    
    :param logger_name: Имя вашего приложения (передавайте __name__)
    :param log_dir: Папка для хранения логов
    :param log_filename: Фиксированное имя файла (если не нужно авто)
    :param file_level: Детализация логов в файле
    :param console_level: Детализация логов в консоли
    :param use_emoji: Добавлять эмодзи в консольные сообщения
    :param formatter: Стиль форматирования сообщений
    :param max_log_age: Удалять логи старше N дней
    :param use_console: Включить вывод в консоль
    :param use_file: Включить запись в файл
    
    :return: Готовый к использованию логгер
    """
    # Создаем логгер с именем приложения
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    
    # Убираем .py из имени если это файл
    app_name = logger_name.replace('.py', '')
    
    # Форматы сообщений
    formats = {
        "basic": "%(asctime)s [%(levelname)s] %(message)s",
        "detailed": "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        "raw": "%(message)s"
    }
    fmt = formats.get(formatter, formats["detailed"])
    
    # Обработчики (куда отправляем логи)
    handlers = []
    
    # 1. ФАЙЛОВЫЙ ОБРАБОТЧИК
    if use_file:
        try:
            # Создаем папку если её нет
            os.makedirs(log_dir, exist_ok=True)
            
            # Автоимя файла если не указано
            if not log_filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_filename = f"{app_name}_{timestamp}.log"
            
            log_path = os.path.join(log_dir, log_filename)
            
            # Очищаем старые логи ЭТОГО приложения
            if max_log_age > 0:
                _clean_app_logs(log_dir, app_name, max_log_age)
            
            # Настраиваем запись в файл
            fh = logging.FileHandler(log_path, encoding='utf-8-sig')
            fh.setLevel(file_level.upper())
            fh.setFormatter(logging.Formatter(fmt))
            handlers.append(fh)
            
        except Exception as e:
            # Если не удалось создать файл - сообщим в консоль
            error_msg = f"Ошибка файлового лога: {str(e)}"
            _fallback_error(logger, error_msg)
            use_file = False
    
    # 2. КОНСОЛЬНЫЙ ОБРАБОТЧИК
    if use_console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(console_level.upper())
        
        # Добавляем эмодзи если включено
        if use_emoji:
            ch.setFormatter(EmojiFormatter(fmt))
        else:
            ch.setFormatter(logging.Formatter(fmt))
        
        handlers.append(ch)
    
    # Применяем обработчики
    for handler in handlers:
        logger.addHandler(handler)
    
    # Сообщаем где хранятся логи
    if use_file:
        logger.info(f"📁 Логи сохраняются в: {os.path.abspath(log_path)}")
    elif not handlers:
        logger.warning("Логирование отключено! Нет активных обработчиков")
    
    return logger

def _clean_app_logs(log_dir: str, app_name: str, max_days: int):
    """Удаляет старые логи ТОЛЬКО для указанного приложения"""
    now = time.time()
    cutoff = now - (max_days * 86400)  # секунд в N днях
    
    # Шаблон поиска: все файлы логов этого приложения
    pattern = os.path.join(log_dir, f"{app_name}_*.log")
    
    for file_path in glob.glob(pattern):
        # Проверяем время изменения файла
        if os.stat(file_path).st_mtime < cutoff:
            try:
                os.remove(file_path)
            except Exception:
                pass  # Не удалось удалить - пропускаем

def _fallback_error(logger: logging.Logger, message: str):
    """Аварийное логирование при критических ошибках"""
    try:
        # Пытаемся вывести через временный обработчик
        temp_handler = logging.StreamHandler(sys.stdout)
        temp_handler.setFormatter(logging.Formatter("🔥 ОШИБКА ЛОГГЕРА: %(message)s"))
        logger.addHandler(temp_handler)
        logger.critical(message)
        logger.removeHandler(temp_handler)
    except Exception:
        # Последнее средство - обычный print
        print(f"🔥 КРИТИЧЕСКАЯ ОШИБКА ЛОГГЕРА: {message}")

# Класс для будущих расширений
class AdvancedLogger(logging.Logger):
    """Базовый класс для продвинутых функций"""
    # Реализуется в следующих версиях
    pass
