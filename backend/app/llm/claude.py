import json

import httpx

from app.config import settings


class ClaudeReasoningClient:
    _SYSTEM_HINT = (
        'You advise an autonomous US-options bot. Trading objective: small consistent daily gains with strict risk; '
        'stop trading for the day once profit or loss caps are hit. Never encourage overriding risk rules. '
        'If the tape is choppy, mean-reverting, or regime is unclear, set chop_warning true and lower confidence. '
        'If volatility or a sudden adverse move is likely, set anomaly_flags (e.g. ["gap_risk","headline_risk"]). '
        'Return compact JSON only with keys: confidence (0-1 float), chop_warning (bool), rationale (string), '
        'anomaly_flags (list of strings).'
    )

    async def explain(self, payload: dict) -> dict:
        if not settings.claude_api_key:
            return {
                'confidence': 0.65,
                'chop_warning': False,
                'rationale': 'No Claude API key configured; neutral fallback so SIM/dev runs unless MIN_ENTRY_CONFIDENCE is set.',
                'anomaly_flags': [],
            }

        body = {
            'model': settings.claude_model,
            'max_tokens': 256,
            'messages': [
                {'role': 'user', 'content': f"{self._SYSTEM_HINT}\n\nContext JSON:\n{json.dumps(payload)}"},
            ],
        }
        headers = {
            'x-api-key': settings.claude_api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post('https://api.anthropic.com/v1/messages', headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

        content_text = ''
        if data.get('content'):
            content_text = data['content'][0].get('text', '{}')
        try:
            parsed = json.loads(content_text)
        except json.JSONDecodeError:
            parsed = {
                'confidence': 0.5,
                'chop_warning': True,
                'rationale': content_text[:200],
                'anomaly_flags': ['unstructured_response'],
            }
        return parsed
