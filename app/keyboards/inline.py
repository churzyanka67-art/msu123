from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_keyboard(rows, revision: str):
    actions = {}
    keyboard = []
    for row in rows:
        buttons = []
        for label, action in row:
            key = f"v:{revision}:{len(actions)}"
            actions[key] = action
            buttons.append(InlineKeyboardButton(text=label, callback_data=key))
        keyboard.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=keyboard), actions
