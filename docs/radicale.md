1. Создать файл пользователей
docker exec -it workflow-radicale htpasswd -B -c /data/users ivan

2. Добавить следующего
docker exec -it workflow-radicale htpasswd -B /data/users petr

3. Выполнять п.3, пока есть пользователи

4. docker restart workflow-radicale

В профиле сотрудник вводит: URL (http://192.168.0.150:5232), логин (ivan), пароль.
В том же меню — ввести вместо URL. Доступ удаляется, события больше не создаются.

Можно не подключать: сотрудник пользуется только текстовым расписанием в боте. Встречи всё равно видны в CalendarEvent, но в календарь не уходят.