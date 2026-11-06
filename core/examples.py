"""Small synthetic questionnaires for onboarding, never real user data."""
from dataclasses import dataclass
from io import BytesIO
import pandas as pd


@dataclass
class ExampleUpload:
    name: str
    data: bytes

    def read(self):
        return self.data

    def getvalue(self):
        return self.data


def sample_uploads():
    output = []
    for period in (1, 2):
        stream = BytesIO()
        pd.DataFrame({
            "学员编号": ["DEMO01", "DEMO02", "DEMO03"],
            "课程整体满意度": [5, 3 + period % 2, 4],
            "课程反馈": ["老师讲解清晰，但课程节奏太快", "希望增加真实案例", "无"],
        }).to_excel(stream, index=False)
        output.append(ExampleUpload(f"合成示例课程_第{period:02d}期.xlsx", stream.getvalue()))
    return output
