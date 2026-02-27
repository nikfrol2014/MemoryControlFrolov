# Гайд по очистителю мусора на AMR (или ПК)
### Для правильной работы демона важно создать правильный конфиг - покопайтесь в нем, он содержит переменные, которые вам, очень вероятно, нужно будет изменить
# Общий случай
# ______________________________
### Сначала узнаем, кто есть мы в системе
```bash
whoami # результат и есть имя, которое нужно вписать в конфиг
# там 2 места куда нужно вписать это имя, вы должны легко их найти ))
```

### Создаем директории
```bash
sudo mkdir -p /usr/local/bin /etc/memory-cleaner /var/log/memory-cleaner
```

### Копируем скрипт и делаем его исполняемым
```bash
sudo cp memory-cleaner.py /usr/local/bin/
sudo chmod +x /usr/local/bin/memory-cleaner.py
```

### Создаем конфиг (или копируем текущий)
```bash
sudo cp config.json /etc/memory-cleaner/
```

### Проверяем корректность
```bash
sudo python3 /usr/local/bin/memory-cleaner.py --config /etc/memory-cleaner/config.json --dry-run
```

### Устанавливаем сервис
```bash
sudo cp memory-cleaner.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable memory-cleaner
sudo systemctl start memory-cleaner
```

### Проверяем статус
```bash
sudo systemctl status memory-cleaner
```

### Смотрим логи
```bash
sudo journalctl -u memory-cleaner -f
```

### Или смотрим файл лога
```bash
sudo tail -f /var/log/memory-cleaner/cleaner.log
```
# ______________________________
## Ручной запуск отчистки

### Находим PID демона
```bash
ps aux | grep memory-cleaner
```

### Отправляем сигнал для ручной очистки
```bash
sudo kill -SIGUSR1 <PID>
```

### Или одной командой
```bash
sudo pkill -SIGUSR1 -f memory-cleaner.py
```

# _____________________________
## Для проверки можно временно изменить пороги в конфиге
### не копируйте эту часть (json не поддерживает комменты - тут они для наглядности)
```json
{
    "warning_threshold_gb": 10,  // заведомо больше свободного места
    "cleanup_threshold_gb": 20   // чтобы сразу сработала очистка
}
```

## Или создать тестовые файлы
```bash
# Создаем старые тестовые файлы
sudo touch -t 202301010000 /tmp/test_old_file.log
sudo dd if=/dev/zero of=/tmp/test_big_file bs=1M count=100

# Проверяем логи
sudo tail -f /var/log/memory-cleaner/cleaner.log
```

# _____________________________
# Как проверить работоспособность?
### Для этого есть гайд (см. [Use_test_ver.md](Use_test_ver.md)) 

# _____________________________
Создал FrolovNM (nikfrol2014).