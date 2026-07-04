# Mock torchvision.transforms.v2 functional helper
class MockFunctional:
    def __getattr__(self, name):
        return None

functional = MockFunctional()
