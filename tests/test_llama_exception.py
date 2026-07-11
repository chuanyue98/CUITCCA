import inspect
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import tests._pathsetup  # noqa: F401


class IdNotFoundExceptionsSignatureTest(unittest.TestCase):
    def test_preserves_wrapped_function_signature(self):
        from exceptions.llama_exception import id_not_found_exceptions

        async def handler(query: str, other: int = 3):
            return query, other

        wrapped = id_not_found_exceptions(handler)

        self.assertEqual(
            inspect.signature(wrapped),
            inspect.signature(handler),
            'FastAPI relies on the wrapper exposing the original signature '
            'to resolve route parameters like Form()/Query() fields.',
        )

    @patch('exceptions.llama_exception.error_logger')
    def test_raises_http_404_on_value_error(self, mock_logger):
        from exceptions.llama_exception import id_not_found_exceptions

        async def failing_handler():
            raise ValueError("something went wrong")

        wrapped = id_not_found_exceptions(failing_handler)

        with self.assertRaises(HTTPException) as ctx:
            import asyncio
            asyncio.run(wrapped())

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(
            ctx.exception.detail,
            "出错了，请换个方式提问吧，如再遇此问题，请联系管理员反馈",
        )
        mock_logger.error.assert_called_once_with("ValueError: something went wrong")

    @patch('exceptions.llama_exception.error_logger')
    def test_passes_through_on_success(self, mock_logger):
        from exceptions.llama_exception import id_not_found_exceptions

        async def success_handler():
            return "ok"

        wrapped = id_not_found_exceptions(success_handler)

        import asyncio
        result = asyncio.run(wrapped())

        self.assertEqual(result, "ok")
        mock_logger.error.assert_not_called()


if __name__ == '__main__':
    unittest.main()