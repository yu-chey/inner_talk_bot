from typing import Dict, List, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class ContextService:
    
    def __init__(self, users_collection, cache=None):
        self.collection = users_collection
        self.cache = cache
    
    def _get_time_of_day(self) -> tuple[str, str]:
        now = datetime.now(timezone.utc)
        hour = now.hour
        
        if 5 <= hour < 12:
            return "утро", "🌅"
        elif 12 <= hour < 17:
            return "день", "☀️"
        elif 17 <= hour < 22:
            return "вечер", "🌆"
        else:
            return "ночь", "🌙"
    
    async def load_user_context(self, user_id: int) -> str:
        cache_key = f"context:{user_id}"
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return cached
        
        try:
            pipeline = [
                {"$match": {"user_id": user_id}},
                {"$facet": {
                    "tests": [
                        {"$match": {"type": "test_result"}},
                        {"$sort": {"finished_at": -1}},
                        {"$limit": 3},
                        {"$project": {
                            "test_title": 1,
                            "test_id": 1,
                            "result": 1,
                            "finished_at": 1
                        }}
                    ],
                    "scores": [
                        {"$match": {"type": "progress_score"}},
                        {"$sort": {"timestamp": -1}},
                        {"$limit": 10},
                        {"$project": {
                            "score": 1,
                            "timestamp": 1
                        }}
                    ]
                }}
            ]
            
            result = await self.collection.aggregate(pipeline).to_list(1)
            
            if not result or not result[0]:
                context = self._format_time_of_day_only()
            else:
                data = result[0]
                context = self._format_context(
                    tests=data.get("tests", []),
                    scores=data.get("scores", [])
                )
            
            if self.cache:
                await self.cache.set(cache_key, context, ttl=300)
            
            return context
        except Exception as e:
            logger.error(f"Error loading user context: {e}")
            return self._format_time_of_day_only()
    
    def _format_time_of_day_only(self) -> str:
        time_of_day, emoji = self._get_time_of_day()
        return f"{emoji} Сейчас {time_of_day} (по UTC)."
    
    def _format_context(self, tests: List[Dict], scores: List[Dict]) -> str:
        parts = [self._format_time_of_day_only()]
        
        if tests:
            parts.append("\n📊 Результаты последних тестов пользователя (это психологические тесты, которые пользователь проходил ранее):")
            for test in tests[:3]:
                parts.append(self._format_test_result(test))
            parts.append("Используй эти результаты для понимания текущего состояния пользователя и его психологических особенностей.")
        
        if scores:
            parts.append("\n📈 Последние оценки прогресса (дневник эмоций):")
            score_strs = []
            score_values = []
            for s in scores[:5]:
                if s.get("timestamp"):
                    date_str = s["timestamp"].strftime("%d.%m.%Y")
                    score = s.get("score", 0)
                    score_strs.append(f"{date_str}: {score}/10")
                    score_values.append(score)
            
            if score_strs:
                parts.append(", ".join(score_strs))
                
                if len(score_values) >= 2:
                    trend = self._calculate_trend(score_values)
                    parts.append(f"({trend})")
        
        return "\n".join(parts)
    
    def _format_test_result(self, test: Dict) -> str:
        result = test.get("result", {})
        test_id = test.get("test_id", "")
        test_title = test.get("test_title", "Неизвестный тест")
        finished_at = test.get("finished_at")
        
        date_str = ""
        if finished_at:
            if isinstance(finished_at, datetime):
                date_str = finished_at.strftime("%d.%m.%Y")
            else:
                try:
                    date_str = datetime.fromisoformat(str(finished_at)).strftime("%d.%m.%Y")
                except:
                    pass
        
        date_prefix = f"[{date_str}] " if date_str else ""
        
        if result.get("type") == "mbti":
            code = result.get("code", "")
            description = result.get("description", "")
            if description:
                short_desc = description[:200] + "..." if len(description) > 200 else description
                return f"- {date_prefix}{test_title}: тип личности {code}. {short_desc}"
            return f"- {date_prefix}{test_title}: тип личности {code}"
        elif "emotional" in test_id:
            averages = result.get("averages", {})
            if averages:
                stress = averages.get("stress", 0)
                anxiety = averages.get("anxiety", 0)
                burnout = averages.get("burnout", 0)
                interpretation = []
                if stress >= 4.0:
                    interpretation.append("высокий уровень стресса")
                elif stress >= 3.0:
                    interpretation.append("умеренный стресс")
                if anxiety >= 4.0:
                    interpretation.append("высокая тревожность")
                elif anxiety >= 3.0:
                    interpretation.append("умеренная тревожность")
                if burnout >= 4.0:
                    interpretation.append("высокий риск выгорания")
                elif burnout >= 3.0:
                    interpretation.append("признаки выгорания")
                
                interp_text = f" ({', '.join(interpretation)})" if interpretation else ""
                return (
                    f"- {date_prefix}{test_title}: "
                    f"стресс {stress:.1f}/5, тревожность {anxiety:.1f}/5, "
                    f"выгорание {burnout:.1f}/5{interp_text}"
                )
        
        verdict = result.get("verdict", "")
        if verdict:
            short_verdict = verdict[:250] + "..." if len(verdict) > 250 else verdict
            return f"- {date_prefix}{test_title}: {short_verdict}"
        
        return f"- {date_prefix}{test_title}: пройден"
    
    def _calculate_trend(self, score_values: List[int]) -> str:
        latest = score_values[0]
        previous = score_values[1] if len(score_values) > 1 else latest
        avg_recent = sum(score_values[:5]) / min(5, len(score_values))
        
        trend_parts = []
        if latest > previous:
            trend_parts.append("тенденция к улучшению")
        elif latest < previous:
            trend_parts.append("тенденция к снижению")
        else:
            trend_parts.append("стабильное состояние")
        
        if avg_recent >= 7:
            trend_parts.append("в целом хорошее состояние")
        elif avg_recent <= 4:
            trend_parts.append("требуется поддержка")
        
        return f"{', '.join(trend_parts)}, среднее за последние оценки: {avg_recent:.1f}/10"

