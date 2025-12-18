from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Dict, List, Tuple, Any


QuestionType = Literal["likert", "mbti_ab"]


@dataclass
class Question:
    text: str
    qtype: QuestionType
    scale: str | None = None
    mbti_dim: str | None = None
    a_is: str | None = None
    b_is: str | None = None



MBTI_SHORT: List[Question] = [
    Question("Мне комфортнее в больших компаниях людей, чем наедине.", "mbti_ab", mbti_dim="EI", a_is="E", b_is="I"),
    Question("Я восполняю энергию в одиночестве, а не в толпе.", "mbti_ab", mbti_dim="EI", a_is="I", b_is="E"),
    Question("Я охотнее начинаю разговор первым.", "mbti_ab", mbti_dim="EI", a_is="E", b_is="I"),
    Question("Я предпочитаю глубинные беседы паре близких людей.", "mbti_ab", mbti_dim="EI", a_is="I", b_is="E"),
    Question("На вечеринках я часто в центре внимания.", "mbti_ab", mbti_dim="EI", a_is="E", b_is="I"),
    Question("Мне больше по душе тихий вечер дома, чем шумные встречи.", "mbti_ab", mbti_dim="EI", a_is="I", b_is="E"),
    Question("Я полагаюсь на факты больше, чем на интуицию.", "mbti_ab", mbti_dim="SN", a_is="S", b_is="N"),
    Question("Мне интереснее возможности и идеи, чем детали текущей реальности.", "mbti_ab", mbti_dim="SN", a_is="N", b_is="S"),
    Question("Я предпочитаю конкретику абстракциям.", "mbti_ab", mbti_dim="SN", a_is="S", b_is="N"),
    Question("Фантазии и альтернативные сценарии меня вдохновляют.", "mbti_ab", mbti_dim="SN", a_is="N", b_is="S"),
    Question("Мне проще учиться на примерах, чем на теориях.", "mbti_ab", mbti_dim="SN", a_is="S", b_is="N"),
    Question("Я часто думаю о будущем и возможном.", "mbti_ab", mbti_dim="SN", a_is="N", b_is="S"),
    Question("Принимая решения, я больше опираюсь на логику, чем на чувства.", "mbti_ab", mbti_dim="TF", a_is="T", b_is="F"),
    Question("Мне важнее гармония отношений, чем строгость аргументов.", "mbti_ab", mbti_dim="TF", a_is="F", b_is="T"),
    Question("Я критикую идею, даже если это может ранить чувства.", "mbti_ab", mbti_dim="TF", a_is="T", b_is="F"),
    Question("Я стараюсь поддержать, даже если решение несовершенно логично.", "mbti_ab", mbti_dim="TF", a_is="F", b_is="T"),
    Question("Правда важнее, чем вежливость.", "mbti_ab", mbti_dim="TF", a_is="T", b_is="F"),
    Question("Сочувствие важнее, чем объективная правота.", "mbti_ab", mbti_dim="TF", a_is="F", b_is="T"),
    Question("Я предпочитаю план и порядок спонтанности.", "mbti_ab", mbti_dim="JP", a_is="J", b_is="P"),
    Question("Мне ближе гибкость и открытость, чем фиксированный план.", "mbti_ab", mbti_dim="JP", a_is="P", b_is="J"),
    Question("Люблю, когда все решено заранее.", "mbti_ab", mbti_dim="JP", a_is="J", b_is="P"),
    Question("Оставляю пространство для внезапных возможностей.", "mbti_ab", mbti_dim="JP", a_is="P", b_is="J"),
    Question("Чек-листы и дедлайны — мои друзья.", "mbti_ab", mbti_dim="JP", a_is="J", b_is="P"),
    Question("Выбираю по настроению, а не по плану.", "mbti_ab", mbti_dim="JP", a_is="P", b_is="J"),
]

EMO_SHORT: List[Question] = [
    Question("Я чувствую напряжение или стресс в течение дня.", "likert", scale="stress"),
    Question("Мне сложно расслабиться.", "likert", scale="stress"),
    Question("Мне трудно сосредоточиться из-за переживаний.", "likert", scale="anxiety"),
    Question("Я часто испытываю чувство беспокойства без явной причины.", "likert", scale="anxiety"),
    Question("Работа/учёба больше не приносит удовольствия.", "likert", scale="burnout"),
    Question("Чувствую истощение даже после отдыха.", "likert", scale="burnout"),
    Question("У меня учащается сердцебиение или потливость при волнении.", "likert", scale="anxiety"),
    Question("Чувствую раздражительность по мелочам.", "likert", scale="stress"),
    Question("Часто откладываю дела из-за отсутствия сил.", "likert", scale="burnout"),
    Question("У меня нарушается сон из-за переживаний.", "likert", scale="anxiety"),
    Question("Часто чувствую себя перегруженным.", "likert", scale="stress"),
    Question("Чувствую цинизм или отчуждение от задач.", "likert", scale="burnout"),
    Question("Нервничаю при мысли о предстоящих делах.", "likert", scale="anxiety"),
    Question("Часто переживаю, что не справлюсь.", "likert", scale="stress"),
    Question("Даже после выходных нет ощущения восстановления.", "likert", scale="burnout"),
    Question("Беспокойство мешает наслаждаться привычными вещами.", "likert", scale="anxiety"),
    Question("Мелкие трудности воспринимаю как серьёзные.", "likert", scale="stress"),
    Question("Есть чувство эмоционального истощения.", "likert", scale="burnout"),
    Question("Легко впадаю в тревожные мысли.", "likert", scale="anxiety"),
    Question("Чувствую постоянное внутреннее напряжение.", "likert", scale="stress"),
]


ATTACH_SHORT: List[Question] = [
    Question("Легко доверяю партнёру и делюсь чувствами.", "likert", scale="secure"),
    Question("Боюсь, что партнёр меня покинет.", "likert", scale="anxious"),
    Question("Избегаю близости и стараюсь держать дистанцию.", "likert", scale="avoidant"),
    Question("Комфортно прошу о поддержке.", "likert", scale="secure"),
    Question("Часто переживаю, что партнёру я не нужен(а).", "likert", scale="anxious"),
    Question("Мне сложно быть уязвимым(ой) рядом с партнёром.", "likert", scale="avoidant"),
    Question("Мне важно сотрудничество и взаимопонимание.", "likert", scale="secure"),
    Question("Сильно тревожусь при задержках ответов/звонков.", "likert", scale="anxious"),
    Question("Предпочитаю решать проблемы в одиночку.", "likert", scale="avoidant"),
    Question("Чувствую себя ценным(ой) в отношениях.", "likert", scale="secure"),
    Question("Постоянно ищу подтверждения любви.", "likert", scale="anxious"),
    Question("Сложно выдерживать эмоциональную близость.", "likert", scale="avoidant"),
    Question("Умею открыто говорить о потребностях.", "likert", scale="secure"),
    Question("Сильно переживаю из-за неопределённости в отношениях.", "likert", scale="anxious"),
    Question("Чаще отстраняюсь, чем иду на сближение.", "likert", scale="avoidant"),
    Question("Чувствую безопасность рядом с партнёром.", "likert", scale="secure"),
    Question("Склонен(на) к ревности и страху потери.", "likert", scale="anxious"),
    Question("Некомфортно проявлять нежность и зависимость.", "likert", scale="avoidant"),
    Question("Легко и спокойно формирую близкие связи.", "likert", scale="secure"),
    Question("Сильно реагирую на малейшие признаки дистанции.", "likert", scale="anxious"),
]

LOVE_SHORT: List[Question] = [
    Question("Мне важны слова поддержки и признания.", "likert", scale="words"),
    Question("Я чувствую любовь через совместное время.", "likert", scale="time"),
    Question("Подарки помогают мне ощущать заботу.", "likert", scale="gifts"),
    Question("Физический контакт особенно важен.", "likert", scale="touch"),
    Question("Действия (помощь, забота) значат для меня больше слов.", "likert", scale="service"),
    Question("Когда меня хвалят, я расцветаю.", "likert", scale="words"),
    Question("Мне нужно качественно проводить время вместе.", "likert", scale="time"),
    Question("Небольшие знаки внимания радуют меня.", "likert", scale="gifts"),
    Question("Объятия/прикосновения делают меня спокойнее.", "likert", scale="touch"),
    Question("Мне важны конкретные дела в мою поддержку.", "likert", scale="service"),
    Question("Слова одобрения придают уверенность.", "likert", scale="words"),
    Question("Мне важно быть вместе без гаджетов.", "likert", scale="time"),
    Question("Приятные сюрпризы — проявление любви.", "likert", scale="gifts"),
    Question("Тактильность в отношениях — необходимость.", "likert", scale="touch"),
    Question("Когда обо мне заботятся делами — это любовь.", "likert", scale="service"),
    Question("Поддержка словами — лучший подарок.", "likert", scale="words"),
    Question("Совместные активности сближают.", "likert", scale="time"),
    Question("Подарки значимы, даже небольшие.", "likert", scale="gifts"),
    Question("Нежность — ключ к близости.", "likert", scale="touch"),
    Question("Помощь в быту/делах — проявление любви.", "likert", scale="service"),
]


MBTI_LONG: List[Question] = [
    *MBTI_SHORT[:6],
    Question("Мне легче заводить новых знакомых, чем поддерживать узкий круг.", "mbti_ab", mbti_dim="EI", a_is="E", b_is="I"),
    Question("Предпочитаю провести вечер наедине с мыслями.", "mbti_ab", mbti_dim="EI", a_is="I", b_is="E"),
    Question("Я часто становлюсь инициатором совместных активностей.", "mbti_ab", mbti_dim="EI", a_is="E", b_is="I"),
    Question("После насыщенного общения мне нужен длительный отдых наедине.", "mbti_ab", mbti_dim="EI", a_is="I", b_is="E"),
    Question("Мне проще высказаться вслух, чем писать.", "mbti_ab", mbti_dim="EI", a_is="E", b_is="I"),
    Question("Я предпочитаю слушать и обдумывать, прежде чем говорить.", "mbti_ab", mbti_dim="EI", a_is="I", b_is="E"),
    *MBTI_SHORT[6:12],
    Question("Конкретные факты важнее общих идей.", "mbti_ab", mbti_dim="SN", a_is="S", b_is="N"),
    Question("Меня вдохновляет то, что ещё только возможно.", "mbti_ab", mbti_dim="SN", a_is="N", b_is="S"),
    Question("Люблю опираться на проверенные методы.", "mbti_ab", mbti_dim="SN", a_is="S", b_is="N"),
    Question("Люблю изобретать новые подходы и концепты.", "mbti_ab", mbti_dim="SN", a_is="N", b_is="S"),
    Question("Детали для меня важнее, чем общая картина.", "mbti_ab", mbti_dim="SN", a_is="S", b_is="N"),
    Question("Общая картина важнее, чем отдельные детали.", "mbti_ab", mbti_dim="SN", a_is="N", b_is="S"),
    *MBTI_SHORT[12:18],
    Question("Решения должны быть прежде всего справедливыми.", "mbti_ab", mbti_dim="TF", a_is="T", b_is="F"),
    Question("Решения должны минимизировать страдания людей.", "mbti_ab", mbti_dim="TF", a_is="F", b_is="T"),
    Question("Я легко указываю на несоответствия и ошибки.", "mbti_ab", mbti_dim="TF", a_is="T", b_is="F"),
    Question("Я учитываю чувства людей даже ценой логики.", "mbti_ab", mbti_dim="TF", a_is="F", b_is="T"),
    Question("Правила важнее исключений.", "mbti_ab", mbti_dim="TF", a_is="T", b_is="F"),
    Question("Исключения важнее правил.", "mbti_ab", mbti_dim="TF", a_is="F", b_is="T"),
    *MBTI_SHORT[18:24],
    Question("Люблю, когда расписание чётко определено.", "mbti_ab", mbti_dim="JP", a_is="J", b_is="P"),
    Question("Предпочитаю оставлять пространство для импровизации.", "mbti_ab", mbti_dim="JP", a_is="P", b_is="J"),
    Question("Закрывать задачи до дедлайна — мой стиль.", "mbti_ab", mbti_dim="JP", a_is="J", b_is="P"),
    Question("Сначала исследую варианты, потом решаюсь.", "mbti_ab", mbti_dim="JP", a_is="P", b_is="J"),
    Question("План лучше корректировать редко.", "mbti_ab", mbti_dim="JP", a_is="J", b_is="P"),
    Question("План — рабочая гипотеза, меняется по ходу.", "mbti_ab", mbti_dim="JP", a_is="P", b_is="J"),
]

EMO_LONG: List[Question] = [
    *EMO_SHORT,
    Question("В течение дня ощущаю внутреннюю напряжённость.", "likert", scale="stress"),
    Question("Легко раздражаюсь и вспыхиваю.", "likert", scale="stress"),
    Question("Трудно восстанавливаться после нагрузок.", "likert", scale="stress"),
    Question("Чувствую, что ресурсов не хватает.", "likert", scale="stress"),
    Question("Бывает сложно остановить поток тревожных мыслей.", "likert", scale="anxiety"),
    Question("Беспокоюсь о будущем сильнее обычного.", "likert", scale="anxiety"),
    Question("Переживания мешают принимать решения.", "likert", scale="anxiety"),
    Question("Чувствую напряжение в теле из‑за тревоги.", "likert", scale="anxiety"),
    Question("Задачи, которые раньше радовали, теперь утомляют.", "likert", scale="burnout"),
    Question("Сложно видеть смысл в работе/учёбе.", "likert", scale="burnout"),
    Question("Трудно начать даже простые дела.", "likert", scale="burnout"),
    Question("Часто хочется отстраниться от обязанностей.", "likert", scale="burnout"),
    Question("Часто ощущаю гонку мыслей.", "likert", scale="anxiety"),
    Question("Малые проблемы воспринимаются как большие.", "likert", scale="stress"),
    Question("После отдыха возвращается утомление.", "likert", scale="burnout"),
    Question("Напряжение влияет на сон и аппетит.", "likert", scale="stress"),
    Question("Волнения появляются без явного повода.", "likert", scale="anxiety"),
    Question("Чувствую эмоциональную опустошённость.", "likert", scale="burnout"),
]

ATTACH_LONG: List[Question] = [
    *ATTACH_SHORT,
    Question("В близких отношениях чувствую стабильность и спокойствие.", "likert", scale="secure"),
    Question("Сильно переживаю, что меня могут отвергнуть.", "likert", scale="anxious"),
    Question("Некомфортно раскрывать личные переживания.", "likert", scale="avoidant"),
    Question("Легко прошу о помощи и поддержке.", "likert", scale="secure"),
    Question("Мне трудно верить в стабильность чувств партнёра.", "likert", scale="anxious"),
    Question("Иногда предпочитаю дистанцироваться.", "likert", scale="avoidant"),
    Question("Чувствую, что могу положиться на партнёра.", "likert", scale="secure"),
    Question("Тревожусь из‑за пауз в общении.", "likert", scale="anxious"),
    Question("Сложно принимать проявления близости.", "likert", scale="avoidant"),
]

LOVE_LONG: List[Question] = [
    *LOVE_SHORT,
    Question("Поддерживающие фразы важны для меня ежедневно.", "likert", scale="words"),
    Question("Совместные дела создают ощущение близости.", "likert", scale="time"),
    Question("Небольшие презенты кажутся тёплым знаком внимания.", "likert", scale="gifts"),
    Question("Прикосновения помогают чувствовать связь.", "likert", scale="touch"),
    Question("Практическая помощь — значимый способ заботы.", "likert", scale="service"),
]


TESTS = {
    "mbti": {
        "title": "MBTI — тип личности",
        "versions": {
            "short": MBTI_SHORT,
            "long": MBTI_LONG,
        },
        "type": "mbti"
    },
    "emotional": {
        "title": "Эмоциональное состояние",
        "versions": {
            "short": EMO_SHORT,
            "long": EMO_LONG,
        },
        "type": "likert_multi"
    },
    "attachment": {
        "title": "Тип привязанности",
        "versions": {
            "short": ATTACH_SHORT,
            "long": ATTACH_LONG,
        },
        "type": "likert_multi"
    },
    "love": {
        "title": "Язык любви",
        "versions": {
            "short": LOVE_SHORT,
            "long": LOVE_LONG,
        },
        "type": "likert_multi"
    },
}


def compute_result(test_id: str, version: str, answers: List[Any]) -> dict:
    if test_id == "mbti":
        questions = TESTS[test_id]["versions"][version]
        counts = {"E": 0, "I": 0, "S": 0, "N": 0, "T": 0, "F": 0, "J": 0, "P": 0}
        for ans, q in zip(answers, questions):
            if q.qtype != "mbti_ab":
                continue
            if ans == "A":
                letter = q.a_is
            else:
                letter = q.b_is
            if letter:
                counts[letter] += 1
        code = ("E" if counts["E"] >= counts["I"] else "I") \
               + ("S" if counts["S"] >= counts["N"] else "N") \
               + ("T" if counts["T"] >= counts["F"] else "F") \
               + ("J" if counts["J"] >= counts["P"] else "P")
        return {
            "type": "mbti",
            "code": code,
            "counts": counts,
            "verdict": f"Ваш тип личности по MBTI: {code}"
        }

    questions = TESTS[test_id]["versions"][version]
    scales: Dict[str, int] = {}
    counts: Dict[str, int] = {}
    for ans, q in zip(answers, questions):
        if q.qtype != "likert" or not q.scale:
            continue
        scales[q.scale] = scales.get(q.scale, 0) + int(ans)
        counts[q.scale] = counts.get(q.scale, 0) + 1

    avg = {k: (scales[k] / max(1, counts[k])) for k in scales}

    if test_id == "emotional":
        verdict = _verdict_emotional(avg)
    elif test_id == "attachment":
        verdict = _verdict_attachment(avg)
    elif test_id == "love":
        verdict = _verdict_love(avg)
    else:
        verdict = "Результаты обработаны."

    return {
        "type": "likert_multi",
        "averages": avg,
        "verdict": verdict
    }


def _verdict_emotional(avg: Dict[str, float]) -> str:
    s = avg.get("stress", 0)
    a = avg.get("anxiety", 0)
    b = avg.get("burnout", 0)
    def lvl(x: float) -> str:
        if x >= 4.0:
            return "высокий"
        if x >= 3.0:
            return "средний"
        return "низкий"
    return (
        "Итог эмоционального состояния:\n"
        f"• Стресс: {lvl(s)} ({s:.1f})\n"
        f"• Тревожность: {lvl(a)} ({a:.1f})\n"
        f"• Выгорание: {lvl(b)} ({b:.1f})\n"
        "Рекомендация: уделите внимание отдыху, гигиене сна и техникам самопомощи."
    )


def _verdict_attachment(avg: Dict[str, float]) -> str:
    sec = avg.get("secure", 0)
    anx = avg.get("anxious", 0)
    avo = avg.get("avoidant", 0)
    dom = max((("Безопасная", sec), ("Тревожная", anx), ("Избегающая", avo)), key=lambda x: x[1])[0]
    return (
        f"Преобладающий тип привязанности: {dom}.\n"
        "Важно помнить: привязанность — это спектр, а не ярлык; она может меняться с опытом."
    )


def _verdict_love(avg: Dict[str, float]) -> str:
    order = sorted(avg.items(), key=lambda x: x[1], reverse=True)
    mapping = {
        "words": "Слова поддержки",
        "time": "Совместное время",
        "gifts": "Подарки",
        "touch": "Физический контакт",
        "service": "Забота делами",
    }
    top = ", ".join(f"{mapping.get(k, k)} ({v:.1f})" for k, v in order)
    return f"Ваши языки любви (по убыванию): {top}."
