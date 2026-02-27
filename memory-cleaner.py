#!/usr/bin/env python3
"""
Memory Cleaner Daemon for AMR
Monitors disk space and performs cleanup when thresholds are reached.
"""
# /usr/local/bin/memory-cleaner.py - создать этот файл тут

import os
import sys
import json
import time
import signal
import logging
import argparse
import subprocess
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Конфигурация по умолчанию
DEFAULT_CONFIG = {
    "mount_point": "/",
    "warning_threshold_gb": 4,
    "cleanup_threshold_gb": 2,
    "check_interval_seconds": 60,
    "log_file": "/var/log/memory-cleaner/cleaner.log",
    "log_max_size_mb": 10,
    "log_backup_count": 5,
    "notification": {
        "enabled": True,
        "display": ":0",
        "user": "robotuser",
        "timeout_ms": 5000
    },
    "cleanup_rules": [
        {
            "path": "/tmp",
            "pattern": "*",
            "max_age_days": 1,
            "recursive": True
        },
        {
            "path": "/var/log",
            "pattern": "*.log",
            "max_age_days": 7,
            "recursive": True,
            "exclude": ["current", "auth.log", "syslog", "kern.log"]
        },
        {
            "path": "/var/cache/apt/archives",
            "pattern": "*.deb",
            "max_age_days": 30,
            "recursive": False
        }
    ]
}


class MemoryCleaner:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self.load_config()
        self.setup_logging()
        self.setup_signal_handlers()
        self.warning_sent = False
        self.cleanup_done_recently = False
        self.running = True

    def load_config(self) -> Dict:
        """Загрузка конфигурации из JSON файла"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                logging.info(f"Configuration loaded from {self.config_path}")
            else:
                logging.warning(f"Config file {self.config_path} not found. Using defaults.")
                config = DEFAULT_CONFIG.copy()
                # Создаем директорию для конфига, если её нет
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(self.config_path, 'w') as f:
                    json.dump(config, f, indent=4)
                logging.info(f"Default configuration saved to {self.config_path}")

            # Проверка наличия обязательных полей
            required_fields = ['mount_point', 'warning_threshold_gb', 'cleanup_threshold_gb',
                               'check_interval_seconds', 'cleanup_rules']
            for field in required_fields:
                if field not in config:
                    raise ValueError(f"Missing required field: {field}")

            return config
        except Exception as e:
            logging.error(f"Error loading config: {e}")
            sys.exit(1)

    def setup_logging(self):
        """Настройка логирования с ротацией"""
        log_file = self.config.get('log_file', '/var/log/memory-cleaner/cleaner.log')
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)

        max_bytes = self.config.get('log_max_size_mb', 10) * 1024 * 1024
        backup_count = self.config.get('log_backup_count', 5)

        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)

        # Добавляем вывод в консоль для отладки (опционально)
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root_logger.addHandler(console)

    def setup_signal_handlers(self):
        """Настройка обработчиков сигналов"""
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        signal.signal(signal.SIGUSR1, self.handle_manual_cleanup)

    def handle_shutdown(self, signum, frame):
        """Обработка сигналов завершения"""
        logging.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def handle_manual_cleanup(self, signum, frame):
        """Обработка сигнала для ручного запуска очистки"""
        logging.info("Received SIGUSR1 - manual cleanup requested")
        self.send_notification("Manual Cleanup", "Starting manual cleanup process...", "normal")
        freed_gb = self.perform_cleanup()
        if freed_gb > 0:
            self.send_notification("Manual Cleanup Complete",
                                   f"Freed {freed_gb:.2f} GB of disk space", "normal")
        else:
            self.send_notification("Manual Cleanup",
                                   "No files were removed", "low")

    def get_free_disk_gb(self, mount_point: str) -> float:
        """Получение свободного места на диске в гигабайтах"""
        try:
            st = os.statvfs(mount_point)
            free_bytes = st.f_bavail * st.f_frsize
            return free_bytes / (1024 ** 3)
        except Exception as e:
            logging.error(f"Error getting free disk space for {mount_point}: {e}")
            return 0.0

    def send_notification(self, title: str, message: str, urgency: str = 'normal'):
        """Отправка всплывающего уведомления через notify-send"""
        if not self.config.get('notification', {}).get('enabled', True):
            return

        notification_config = self.config.get('notification', {})
        user = notification_config.get('user')
        display = notification_config.get('display', ':0')
        timeout = notification_config.get('timeout_ms', 5000)

        if not user:
            logging.warning("Notification user not specified, skipping")
            return

        try:
            # Получаем UID пользователя
            uid = subprocess.check_output(['id', '-u', user]).decode().strip()
            bus_address = f'unix:path=/run/user/{uid}/bus'

            # Формируем команду с правильным окружением
            cmd = [
                'sudo', '-u', user,
                f'DISPLAY={display}',
                f'DBUS_SESSION_BUS_ADDRESS={bus_address}',
                'notify-send',
                '-t', str(timeout),
                '-u', urgency,
                title,
                message
            ]

            # Пытаемся выполнить
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                logging.error(f"Failed to send notification: {result.stderr}")
        except subprocess.TimeoutExpired:
            logging.error("Notification command timed out")
        except Exception as e:
            logging.error(f"Error sending notification: {e}")

    def cleanup_by_rule(self, rule: Dict) -> Tuple[int, int]:
        """
        Очистка по одному правилу
        Возвращает (количество удаленных файлов, освобождено байт)
        """
        path = Path(rule['path'])
        if not path.exists():
            logging.warning(f"Path {path} does not exist, skipping rule")
            return 0, 0

        pattern = rule.get('pattern', '*')
        max_age_days = rule.get('max_age_days', 7)
        recursive = rule.get('recursive', True)
        exclude = set(rule.get('exclude', []))

        # Проверка на опасные пути
        dangerous_paths = ['/', '/bin', '/sbin', '/etc', '/boot', '/dev', '/proc', '/sys']
        if str(path) in dangerous_paths:
            logging.error(f"Refusing to clean dangerous path: {path}")
            return 0, 0

        now = time.time()
        max_age_seconds = max_age_days * 24 * 3600
        removed_count = 0
        freed_bytes = 0

        try:
            # Поиск файлов
            if recursive:
                files = list(path.rglob(pattern))
            else:
                files = list(path.glob(pattern))

            for file_path in files:
                if not file_path.is_file():
                    continue

                # Проверка исключений
                if file_path.name in exclude:
                    continue

                # Проверка возраста файла
                try:
                    file_age = now - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        size = file_path.stat().st_size
                        file_path.unlink()
                        removed_count += 1
                        freed_bytes += size
                        logging.debug(f"Removed: {file_path} (age: {file_age / 3600:.1f} hours)")
                except (OSError, PermissionError) as e:
                    logging.warning(f"Cannot remove {file_path}: {e}")

        except Exception as e:
            logging.error(f"Error during cleanup in {path}: {e}")

        return removed_count, freed_bytes

    def perform_cleanup(self) -> float:
        """
        Выполнение очистки по всем правилам
        Возвращает освобождено гигабайт
        """
        logging.info("Starting cleanup process...")
        total_removed = 0
        total_freed_bytes = 0

        rules = self.config.get('cleanup_rules', [])
        if not rules:
            logging.warning("No cleanup rules defined")
            return 0.0

        for i, rule in enumerate(rules, 1):
            try:
                logging.info(f"Processing rule {i}: {rule.get('path')}")
                cnt, freed = self.cleanup_by_rule(rule)
                total_removed += cnt
                total_freed_bytes += freed
                if cnt > 0:
                    logging.info(f"Rule {i}: removed {cnt} files, freed {freed / (1024 ** 3):.2f} GB")
            except Exception as e:
                logging.error(f"Error in rule {i}: {e}")

        freed_gb = total_freed_bytes / (1024 ** 3)
        logging.info(f"Cleanup completed: removed {total_removed} files, freed {freed_gb:.2f} GB")

        return freed_gb

    def run(self):
        """Основной цикл демона"""
        logging.info("Memory Cleaner Daemon started")
        logging.info(f"Configuration: warning={self.config['warning_threshold_gb']}GB, "
                     f"cleanup={self.config['cleanup_threshold_gb']}GB, "
                     f"interval={self.config['check_interval_seconds']}s")

        self.send_notification("Memory Cleaner Started",
                               f"Monitoring {self.config['mount_point']} every {self.config['check_interval_seconds']}s",
                               "low")

        while self.running:
            try:
                mount_point = self.config['mount_point']
                free_gb = self.get_free_disk_gb(mount_point)

                if free_gb == 0:
                    logging.error(f"Cannot get free space for {mount_point}")
                    time.sleep(self.config['check_interval_seconds'])
                    continue

                logging.info(f"Free space on {mount_point}: {free_gb:.2f} GB")

                # Проверка предупредительного порога
                warn_gb = self.config['warning_threshold_gb']
                if free_gb <= warn_gb and not self.warning_sent:
                    self.send_notification(
                        "⚠️ Low Disk Space Warning",
                        f"Only {free_gb:.2f} GB left on {mount_point}",
                        "critical"
                    )
                    self.warning_sent = True
                    logging.warning(f"Warning threshold reached: {free_gb:.2f} GB <= {warn_gb} GB")
                elif free_gb > warn_gb and self.warning_sent:
                    self.send_notification(
                        "✅ Disk Space Normalized",
                        f"Free space restored to {free_gb:.2f} GB on {mount_point}",
                        "low"
                    )
                    self.warning_sent = False
                    logging.info(f"Free space recovered above warning threshold: {free_gb:.2f} GB")

                # Проверка порога очистки
                clean_gb = self.config['cleanup_threshold_gb']
                if free_gb <= clean_gb:
                    logging.warning(f"Cleanup threshold reached: {free_gb:.2f} GB <= {clean_gb} GB")

                    self.send_notification(
                        "🧹 Starting Automatic Cleanup",
                        f"Free space is critically low ({free_gb:.2f} GB). Cleaning up...",
                        "critical"
                    )

                    freed_gb = self.perform_cleanup()

                    # Проверяем результат после очистки
                    new_free = self.get_free_disk_gb(mount_point)

                    if new_free > clean_gb:
                        self.send_notification(
                            "✅ Cleanup Successful",
                            f"Freed {freed_gb:.2f} GB. Now free: {new_free:.2f} GB",
                            "normal"
                        )
                        logging.info(f"Cleanup successful: {new_free:.2f} GB free")
                    else:
                        self.send_notification(
                            "⚠️ Cleanup Insufficient",
                            f"Still low on space: {new_free:.2f} GB after removing {freed_gb:.2f} GB",
                            "critical"
                        )
                        logging.warning(f"Cleanup insufficient: {new_free:.2f} GB free")

                    self.cleanup_done_recently = True

                # Ждем до следующей проверки
                for _ in range(self.config['check_interval_seconds']):
                    if not self.running:
                        break
                    time.sleep(1)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.exception("Unhandled exception in main loop")
                time.sleep(self.config['check_interval_seconds'])

        logging.info("Memory Cleaner Daemon stopped")
        self.send_notification("Memory Cleaner Stopped", "Daemon has been stopped", "low")


def main():
    parser = argparse.ArgumentParser(description='Memory Cleaner Daemon for AMR')
    parser.add_argument('--config', '-c',
                        default='/etc/memory-cleaner/config.json',
                        help='Path to configuration file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Dry run - only log what would be deleted')
    args = parser.parse_args()

    # Если указан dry-run, можно изменить режим (для простоты пока не реализовано)
    if args.dry_run:
        print("Dry run mode - no files will be actually deleted")
        # Здесь можно добавить логику для dry-run

    cleaner = MemoryCleaner(args.config)

    try:
        cleaner.run()
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt")
    except Exception as e:
        logging.exception("Fatal error")
        sys.exit(1)


if __name__ == '__main__':
    main()