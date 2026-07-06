import inspect
import unittest

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)

from exceptions.llama_exception import id_not_found_exceptions


class IdNotFoundExceptionsSignatureTest(unittest.TestCase):
    def test_preserves_wrapped_function_signature(self):
        async def handler(query: str, other: int = 3):
            return query, other

        wrapped = id_not_found_exceptions(handler)

        self.assertEqual(
            inspect.signature(wrapped),
            inspect.signature(handler),
            'FastAPI relies on the wrapper exposing the original signature '
            'to resolve route parameters like Form()/Query() fields.',
        )


if __name__ == '__main__':
    unittest.main()
