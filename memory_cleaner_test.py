#!/usr/bin/env python3
"""
Memory Cleaner Daemon - ТЕСТОВАЯ ВЕРСИЯ
Для безопасного тестирования на изолированных директориях
"""

import os
import sys
import json
import time
import signal
import logging
import argparse
import subprocess
import shutil
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# Цвета для вывода (опционально)
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class TestMemoryCleaner:
    def __init__(self, config_path: str, dry_run: bool = True, verbose: bool = False):
        """
        Инициализация тестовой версии
        :param config_path: путь к конфигурационному файлу
        :param dry_run: если True, файлы не удаляются (только вывод)
        :param verbose: подробный вывод
        """
        self.config_path = config_path
        self.dry_run = dry_run
        self.verbose = verbose
        self.config = self.load_config()
        self.setup_logging()
        self.setup_signal_handlers()
        self.warning_sent = False
        self.cleanup_done = False
        self.running = True

        # Статистика для тестирования
        self.stats = {
            'checks_performed': 0,
            'cleanups_performed': 0,
            'files_removed': 0,
            'space_freed_mb': 0,
            'errors': 0
        }

    def load_config(self) -> Dict:
        """Загрузка конфигурации"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                self.print_colored(f"✓ Конфигурация загружена из {self.config_path}", Colors.GREEN)
                return config
            else:
                self.print_colored(f"✗ Конфиг {self.config_path} не найден, создаю тестовый...", Colors.YELLOW)
                return self.create_test_config()
        except Exception as e:
            self.print_colored(f"✗ Ошибка загрузки конфига: {e}", Colors.RED)
            sys.exit(1)

    def create_test_config(self) -> Dict:
        """Создание тестового конфига по умолчанию"""
        config = {
            "mount_point": "/",
            "warning_threshold_gb": 5,
            "cleanup_threshold_gb": 3,
            "check_interval_seconds": 30,
            "log_file": "/tmp/memory_cleaner_test.log",
            "log_max_size_mb": 5,
            "log_backup_count": 2,
            "notification": {
                "enabled": False,
                "display": ":0",
                "user": os.environ.get('USER', 'unknown'),
                "timeout_ms": 3000
            },
            "cleanup_rules": [
                {
                    "name": "Тестовые временные файлы",
                    "path": os.path.expanduser("~/test_cleanup/temp"),
                    "pattern": "*.tmp",
                    "max_age_days": 1,
                    "recursive": True
                },
                {
                    "name": "Тестовые логи",
                    "path": os.path.expanduser("~/test_cleanup/logs"),
                    "pattern": "*.log",
                    "max_age_days": 3,
                    "recursive": True,
                    "exclude": ["current.log", "important.log"]
                },
                {
                    "name": "Тестовый кэш",
                    "path": os.path.expanduser("~/test_cleanup/cache"),
                    "pattern": "*",
                    "max_age_days": 2,
                    "recursive": True
                }
            ]
        }

        # Сохраняем конфиг
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=4)

        self.print_colored(f"✓ Создан тестовый конфиг: {self.config_path}", Colors.GREEN)
        return config

    def setup_logging(self):
        """Настройка логирования"""
        log_file = self.config.get('log_file', '/tmp/memory_cleaner_test.log')

        # Создаем handler для файла
        max_bytes = self.config.get('log_max_size_mb', 5) * 1024 * 1024
        backup_count = self.config.get('log_backup_count', 2)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )

        # Создаем handler для консоли
        console_handler = logging.StreamHandler()

        # Настраиваем формат
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # Настраиваем корневой логгер
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

    def setup_signal_handlers(self):
        """Обработчики сигналов для тестов"""
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        signal.signal(signal.SIGUSR1, self.handle_manual_cleanup)

    def handle_shutdown(self, signum, frame):
        """Завершение работы"""
        self.print_colored(f"\nПолучен сигнал {signum}, завершаю работу...", Colors.YELLOW)
        self.print_stats()
        self.running = False

    def handle_manual_cleanup(self, signum, frame):
        """Ручной запуск очистки"""
        self.print_colored("\n🔄 Ручной запуск очистки!", Colors.CYAN)
        freed_mb = self.perform_cleanup()
        if freed_mb > 0:
            self.print_colored(f"✓ Очистка завершена, освобождено {freed_mb:.2f} МБ", Colors.GREEN)

    def print_colored(self, message: str, color: str = Colors.RESET, bold: bool = False):
        """Цветной вывод в консоль"""
        if bold:
            print(f"{Colors.BOLD}{color}{message}{Colors.RESET}")
        else:
            print(f"{color}{message}{Colors.RESET}")

    def get_free_disk_gb(self, mount_point: str) -> float:
        """Получение свободного места"""
        try:
            st = os.statvfs(mount_point)
            free_bytes = st.f_bavail * st.f_frsize
            return free_bytes / (1024 ** 3)
        except Exception as e:
            logging.error(f"Ошибка получения места на {mount_point}: {e}")
            return 0.0

    def create_test_files(self):
        """Создание тестовых файлов для проверки"""
        self.print_colored("\n📁 Создание тестовых файлов...", Colors.BLUE)

        base_dir = os.path.expanduser("~/test_cleanup")
        dirs = ['temp', 'logs', 'cache', 'important']

        # Создаем директории
        for dir_name in dirs:
            os.makedirs(os.path.join(base_dir, dir_name), exist_ok=True)

        now = time.time()

        # Создаем файлы разного возраста
        test_files = [
            # (путь, имя, возраст в днях, размер в МБ)
            ('temp', 'old.tmp', 5, 1),
            ('temp', 'new.tmp', 0, 2),
            ('temp', 'very_old.tmp', 10, 3),
            ('logs', 'old.log', 7, 1),
            ('logs', 'current.log', 0, 4),
            ('logs', 'important.log', 2, 5),
            ('logs', 'debug.log', 4, 1),
            ('cache', 'cache1.bin', 3, 10),
            ('cache', 'cache2.bin', 1, 20),
            ('cache', 'old_cache.bin', 8, 15),
            ('important', 'dont_delete.txt', 30, 1),
        ]

        for dir_name, filename, age_days, size_mb in test_files:
            file_path = os.path.join(base_dir, dir_name, filename)

            # Создаем файл с указанным размером
            with open(file_path, 'wb') as f:
                f.write(b'0' * (size_mb * 1024 * 1024))

            # Устанавливаем время модификации
            mod_time = now - (age_days * 24 * 3600)
            os.utime(file_path, (mod_time, mod_time))

            age_str = f"{age_days} дн." if age_days > 0 else "новый"
            self.print_colored(f"  ✓ Создан: {filename} ({size_mb} МБ, {age_str})", Colors.GREEN)

        self.print_colored(f"✓ Тестовые файлы созданы в {base_dir}", Colors.GREEN)

    def cleanup_by_rule(self, rule: Dict) -> Tuple[int, int]:
        """
        Очистка по правилу
        Возвращает (количество удаленных, освобождено байт)
        """
        path = Path(rule['path'])
        if not path.exists():
            logging.warning(f"Путь не существует: {path}")
            return 0, 0

        pattern = rule.get('pattern', '*')
        max_age_days = rule.get('max_age_days', 7)
        recursive = rule.get('recursive', True)
        exclude = set(rule.get('exclude', []))
        rule_name = rule.get('name', str(path))

        self.print_colored(f"\n  Правило: {rule_name}", Colors.CYAN)
        self.print_colored(f"  Путь: {path}", Colors.CYAN)
        self.print_colored(f"  Паттерн: {pattern}, макс. возраст: {max_age_days} дн.", Colors.CYAN)

        now = time.time()
        max_age_seconds = max_age_days * 24 * 3600
        removed_count = 0
        freed_bytes = 0
        files_to_delete = []

        try:
            # Поиск файлов
            if recursive:
                files = list(path.rglob(pattern))
            else:
                files = list(path.glob(pattern))

            # Анализируем файлы
            for file_path in files:
                if not file_path.is_file():
                    continue

                if file_path.name in exclude:
                    self.print_colored(f"  ⚠ Исключен: {file_path.name}", Colors.YELLOW)
                    continue

                try:
                    file_age = now - file_path.stat().st_mtime
                    age_days = file_age / 3600 / 24
                    size = file_path.stat().st_size

                    if file_age > max_age_seconds:
                        files_to_delete.append((file_path, size, age_days))
                        if not self.dry_run:
                            file_path.unlink()
                            removed_count += 1
                            freed_bytes += size
                    else:
                        if self.verbose:
                            self.print_colored(f"  • Слишком новый: {file_path.name} ({age_days:.1f} дн.)", Colors.BLUE)

                except Exception as e:
                    logging.warning(f"Ошибка обработки {file_path}: {e}")
                    self.stats['errors'] += 1

            # Выводим информацию о файлах для удаления
            if files_to_delete:
                self.print_colored(f"  Найдено файлов для удаления: {len(files_to_delete)}", Colors.YELLOW)
                total_size = sum(size for _, size, _ in files_to_delete)
                self.print_colored(f"  Общий размер: {total_size / (1024 ** 2):.2f} МБ", Colors.YELLOW)

                if self.verbose:
                    for file_path, size, age_days in sorted(files_to_delete, key=lambda x: x[2], reverse=True):
                        size_mb = size / (1024 ** 2)
                        self.print_colored(f"    • {file_path.name} ({size_mb:.2f} МБ, {age_days:.1f} дн.)", Colors.RED)
            else:
                self.print_colored(f"  Файлов для удаления не найдено", Colors.GREEN)

            if self.dry_run and files_to_delete:
                self.print_colored(f"  [DRY RUN] Было бы удалено {len(files_to_delete)} файлов", Colors.YELLOW)

        except Exception as e:
            logging.error(f"Ошибка при очистке {path}: {e}")
            self.stats['errors'] += 1

        return removed_count, freed_bytes

    def perform_cleanup(self) -> float:
        """
        Выполнение очистки
        Возвращает освобождено МБ
        """
        self.print_colored(f"\n{'=' * 60}", Colors.BOLD)
        self.print_colored("🧹 ЗАПУСК ОЧИСТКИ", Colors.BOLD)
        if self.dry_run:
            self.print_colored("📝 РЕЖИМ DRY RUN (файлы НЕ удаляются)", Colors.YELLOW)
        self.print_colored(f"{'=' * 60}", Colors.BOLD)

        total_removed = 0
        total_freed_bytes = 0
        start_time = time.time()

        rules = self.config.get('cleanup_rules', [])
        if not rules:
            self.print_colored("⚠ Нет правил очистки", Colors.YELLOW)
            return 0.0

        for i, rule in enumerate(rules, 1):
            try:
                cnt, freed = self.cleanup_by_rule(rule)
                total_removed += cnt
                total_freed_bytes += freed
            except Exception as e:
                logging.error(f"Ошибка в правиле {i}: {e}")
                self.stats['errors'] += 1

        elapsed = time.time() - start_time
        freed_mb = total_freed_bytes / (1024 ** 2)

        # Обновляем статистику
        self.stats['cleanups_performed'] += 1
        self.stats['files_removed'] += total_removed
        self.stats['space_freed_mb'] += freed_mb

        self.print_colored(f"\n{'=' * 60}", Colors.BOLD)
        self.print_colored(f"📊 РЕЗУЛЬТАТЫ ОЧИСТКИ:", Colors.BOLD)
        self.print_colored(f"  Удалено файлов: {total_removed}", Colors.GREEN if total_removed > 0 else Colors.RESET)
        self.print_colored(f"  Освобождено: {freed_mb:.2f} МБ", Colors.GREEN if freed_mb > 0 else Colors.RESET)
        self.print_colored(f"  Время выполнения: {elapsed:.1f} сек", Colors.RESET)
        self.print_colored(f"{'=' * 60}\n", Colors.BOLD)

        return freed_mb

    def check_disk_space(self):
        """Проверка свободного места"""
        self.stats['checks_performed'] += 1

        mount_point = self.config['mount_point']
        free_gb = self.get_free_disk_gb(mount_point)

        warn_gb = self.config['warning_threshold_gb']
        clean_gb = self.config['cleanup_threshold_gb']

        # Специально для тестов - показываем больше информации
        self.print_colored(f"\n📊 Проверка #{self.stats['checks_performed']}", Colors.BOLD)
        self.print_colored(f"  Свободно на {mount_point}: {free_gb:.2f} ГБ", Colors.RESET)
        self.print_colored(f"  Порог предупреждения: {warn_gb} ГБ",
                           Colors.YELLOW if free_gb <= warn_gb else Colors.GREEN)
        self.print_colored(f"  Порог очистки: {clean_gb} ГБ",
                           Colors.RED if free_gb <= clean_gb else Colors.GREEN)

        # Проверка порогов
        if free_gb <= warn_gb and not self.warning_sent:
            self.print_colored(f"\n⚠ ВНИМАНИЕ: Мало места ({free_gb:.2f} ГБ)!", Colors.YELLOW)
            self.warning_sent = True

        if free_gb <= clean_gb:
            self.print_colored(f"\n🔴 КРИТИЧЕСКИ: Запуск очистки...", Colors.RED)
            freed_mb = self.perform_cleanup()

            if freed_mb > 0:
                self.cleanup_done = True
                self.warning_sent = False

    def print_stats(self):
        """Вывод статистики тестирования"""
        self.print_colored(f"\n{'=' * 60}", Colors.BOLD)
        self.print_colored("📈 СТАТИСТИКА ТЕСТИРОВАНИЯ", Colors.BOLD)
        self.print_colored(f"{'=' * 60}", Colors.BOLD)
        self.print_colored(f"  Проверок выполнено: {self.stats['checks_performed']}", Colors.RESET)
        self.print_colored(f"  Очисток запущено: {self.stats['cleanups_performed']}", Colors.RESET)
        self.print_colored(f"  Файлов удалено: {self.stats['files_removed']}", Colors.RESET)
        self.print_colored(f"  Места освобождено: {self.stats['space_freed_mb']:.2f} МБ", Colors.RESET)
        self.print_colored(f"  Ошибок: {self.stats['errors']}",
                           Colors.RED if self.stats['errors'] > 0 else Colors.GREEN)
        self.print_colored(f"{'=' * 60}\n", Colors.BOLD)

    def interactive_menu(self):
        """Интерактивное меню для тестирования"""
        while True:
            self.print_colored(f"\n{'=' * 60}", Colors.BOLD)
            self.print_colored("🔧 ТЕСТОВОЕ МЕНЮ", Colors.BOLD)
            self.print_colored(f"{'=' * 60}", Colors.BOLD)
            self.print_colored("1. Проверить свободное место", Colors.RESET)
            self.print_colored("2. Запустить очистку сейчас", Colors.RESET)
            self.print_colored("3. Создать тестовые файлы", Colors.RESET)
            self.print_colored("4. Показать статистику", Colors.RESET)
            self.print_colored("5. Показать конфигурацию", Colors.RESET)
            self.print_colored("6. Переключить DRY RUN режим", Colors.RESET)
            self.print_colored("7. Запустить автоматический режим (цикл)", Colors.RESET)
            self.print_colored("0. Выход", Colors.RESET)

            choice = input("\nВыберите действие: ").strip()

            if choice == '1':
                self.check_disk_space()
            elif choice == '2':
                self.perform_cleanup()
            elif choice == '3':
                self.create_test_files()
            elif choice == '4':
                self.print_stats()
            elif choice == '5':
                self.print_colored("\n📋 ТЕКУЩАЯ КОНФИГУРАЦИЯ:", Colors.CYAN)
                print(json.dumps(self.config, indent=2, ensure_ascii=False))
            elif choice == '6':
                self.dry_run = not self.dry_run
                self.print_colored(f"✓ DRY RUN режим: {'ВКЛ' if self.dry_run else 'ВЫКЛ'}",
                                   Colors.YELLOW if self.dry_run else Colors.GREEN)
            elif choice == '7':
                self.run_auto_mode()
            elif choice == '0':
                self.print_stats()
                self.print_colored("👋 Завершение тестирования", Colors.GREEN)
                break

    def run_auto_mode(self):
        """Автоматический режим с циклическими проверками"""
        interval = self.config.get('check_interval_seconds', 30)
        self.print_colored(f"\n🔄 Запуск автоматического режима (интервал {interval} сек)", Colors.GREEN)
        self.print_colored("Нажмите Ctrl+C для остановки\n", Colors.YELLOW)

        try:
            while self.running:
                self.check_disk_space()

                # Обратный отсчет
                for i in range(interval, 0, -1):
                    if not self.running:
                        break
                    print(f"\rСледующая проверка через {i} сек...", end='', flush=True)
                    time.sleep(1)
                print()

        except KeyboardInterrupt:
            self.print_colored("\n\n⏹ Автоматический режим остановлен", Colors.YELLOW)

    def run_once(self):
        """Однократная проверка и очистка"""
        self.print_colored("\n🔍 Однократная проверка", Colors.BOLD)
        self.check_disk_space()
        self.print_stats()


def main():
    parser = argparse.ArgumentParser(description='Memory Cleaner - ТЕСТОВАЯ ВЕРСИЯ')
    parser.add_argument('--config', '-c',
                        default=os.path.expanduser('~/memory_cleaner_test.json'),
                        help='Путь к конфигурационному файлу')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Режим без реального удаления (по умолчанию включен)')
    parser.add_argument('--no-dry-run', action='store_false', dest='dry_run',
                        help='РЕАЛЬНОЕ УДАЛЕНИЕ (осторожно!)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Подробный вывод')
    parser.add_argument('--create-files', action='store_true',
                        help='Создать тестовые файлы перед запуском')
    parser.add_argument('--once', action='store_true',
                        help='Выполнить одну проверку и завершиться')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Интерактивный режим с меню')

    args = parser.parse_args()

    print(f"""
{Colors.CYAN}╔══════════════════════════════════════════════════════════╗
║     MEMORY CLEANER - ТЕСТОВАЯ ВЕРСИЯ                      ║
╚══════════════════════════════════════════════════════════╝{Colors.RESET}
    """)

    # Создаем экземпляр тестового очистителя
    cleaner = TestMemoryCleaner(
        config_path=args.config,
        dry_run=args.dry_run,
        verbose=args.verbose
    )

    # Создаем тестовые файлы если нужно
    if args.create_files:
        cleaner.create_test_files()

    # Запускаем в соответствующем режиме
    try:
        if args.interactive:
            cleaner.interactive_menu()
        elif args.once:
            cleaner.run_once()
        else:
            cleaner.run_auto_mode()
    except KeyboardInterrupt:
        cleaner.print_colored("\n\n👋 Тестирование прервано пользователем", Colors.YELLOW)
        cleaner.print_stats()
    except Exception as e:
        cleaner.print_colored(f"\n❌ Ошибка: {e}", Colors.RED)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())