import asyncio
import json
import requests
import logging


from aiogram import Bot, Dispatcher
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

bot = Bot(token='your_token')
config_file = 'config.json'
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)


class Register(StatesGroup):
    name = State()
    api_key = State()


async def main():
    await dp.start_polling(bot)


def load_config():
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_config(config):
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)


def validate_api_key(api_key):
    try:
        url = 'https://statistics-api.wildberries.ru/api/v1/supplier/sales'
        headers = {'Authorization': f'{api_key}'}
        params = {'dateFrom': '2024-01-01'}
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return True
    except Exception:
        return False


def get_sales_report(api_key, start_date, end_date):
    url = "https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod"
    headers = {'Authorization': f'{api_key}'}
    params = {
        'dateFrom': start_date,
        'dateTo': end_date,

    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    return None


@dp.message(Command('start'))
async def cmd_start(message: Message):
    await message.reply("Привет! Я бот для аналитики продаж на Wildberries. Используйте /help для просмотра доступных команд.")


@dp.message(Command('help'))
async def cmd_help(message: Message):
    help_text = (
        "/addshop - Добавить магазин\n"
        "/delshop - Удалить магазин\n"
        "/shops - Список магазинов\n"
        "/report - Получить отчет о продажах\n"
    )
    await message.reply(help_text)


@dp.message(Command('addshop'))
async def cmd_add_shop(message: Message, state: FSMContext):
    await state.set_state(Register.name)
    await message.answer('Введите имя вашего магазина: ')


@dp.message(Register.name)
async def register_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(Register.api_key)
    await message.answer('Введите API ключ: ')


@dp.message(Register.api_key)
async def register_api_key(message: Message, state: FSMContext):
    await state.update_data(api_key=message.text)
    data = await state.get_data()

    if validate_api_key(data["api_key"]):
        await message.answer(f'Имя магазина: {data["name"]}\nВаш API ключ: {data["api_key"]}')
        await state.clear()

        shop_name = data["name"]
        api_key = data["api_key"]
        config = load_config()
        config['shops'].append({
            'name': shop_name,
            'api_key': api_key
        })
        save_config(config)
        await message.reply(f"Магазин '{shop_name}' успешно добавлен!")
    else:
        await message.answer('Неверный ключ API. Попробуйте снова')
        await state.clear()


@dp.message(Command('delshop'))
async def delete_shop(message: Message):
    shops = load_config()
    if not shops:
        await message.answer("Нет сохраненных магазинов.")
        return


@dp.message(Register.name)
async def confirm_delete(message: Message, state: FSMContext):
    await message.answer('Введите имя магазина для удаления')
    data = await state.get_data()
    if data['name'] == message.text:
        shops = load_config()
        shop_to_delete = next((shop for shop in shops if shop['name'] == Register.name), None)

        if shop_to_delete:
            shops.remove(shop_to_delete)
            save_config(shops)
            await message.answer(f"Магазин {Register.name} успешно удален.")
        else:
            await message.answer("Магазин не найден.")
    else:
        await message.answer("Магазин не найден.")


@dp.message(Command('shops'))
async def list_shops(message: Message):
    config = load_config()
    shops = []

    for i, shop in enumerate(config['shops']):
        shops.append(shop['name'])

    shop_list = "\n".join([shop for shop in shops])
    if not shops:
        await message.answer("Нет сохраненных магазинов.")
    else:
       await message.answer(f"Список магазинов:\n{shop_list}")


@dp.message(Command('report'))
async def cmd_report(message: Message):
    config = load_config()
    shops = config.get('shops', [])
    if not shops:
        await message.reply("У вас нет добавленных магазинов.")
        return

    keyboard = InlineKeyboardMarkup()
    for i, shop in enumerate(config['shops']):
        button = InlineKeyboardButton(shop['name'], callback_data=f'report_{i}')
        keyboard.add(button)

    await message.reply("Выберите магазин для отчета:", reply_markup=keyboard)


@dp.callback_query(lambda c: c.data.startswith('report_'))
async def process_report(callback: CallbackQuery):
    shop_name = callback.data[7:]
    config = load_config()
    shop = next((s for s in config['shops'] if s['name'] == shop_name), None)
    if not shop:
        await bot.answer_callback_query(callback.id)
        return

    await bot.answer_callback_query(callback.id)
    await bot.send_message(callback.from_user.id, "Введите период для отчета (например, 'сегодня', 'вчера' или произвольный период)")

    @dp.message(lambda msg: len(msg.text) > 0)
    async def get_period(msg: Message):
        period = msg.text.lower()
        if period == 'сегодня':
            start_date = end_date = '2023-01-07'
        elif period == 'вчера':
            start_date = end_date = '2023-01-06'
        else:
            await msg.reply("Введите даты начала и окончания периода (в формате: YYYY-MM-DD)")
            return

        sales_data = get_sales_report(shop['api_key'], start_date, end_date)
        if not sales_data:
            await msg.reply("Не удалось получить данные. Попробуйте позже.")
            return

        total_sales = sum(sales_data.get('quantity') * sales_data.get('retail_price'))
        total_qty = sum(sales_data.get('quantity'))

        report = f"Отчет по магазину {shop_name}\n"
        report += f"Общая сумма продаж: {total_sales}\n"
        report += f"Комиссия Wildberries: {sum(sales_data.get('commission_percent', 0))}\n"
        report += f"Скидки Wildberries: {sum(sales_data.get('ppvz_spp_prc', 0))}\n"
        report += f"Комиссия эквайринга: {sum(sales_data.get('acquiring_percent', 0))}\n"
        report += f"Стоимость логистики: {sum(sales_data.get('delivery_rub', 0))}\n"
        report += f"Стоимость хранения: {sum(sales_data.get('storage_fee', 0))}\n"
        report += f"Количество проданных единиц: {total_qty}\n"
        report += f"Средняя цена продажи: {total_sales/total_qty}\n"
        await msg.reply(report)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Бот выключен')