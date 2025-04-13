from typing import Any, List
import numpy as np
from PIL import Image
from abc import ABC, abstractmethod
# from mmengine import Registry

# VERBALIZER = Registry('verbalizer', scope='mmengine')

class Verbalizer(ABC):
    
    @abstractmethod
    def __call__(self, video_path: str):
        pass

    # @abstractmethod
    # def batch_verbalize(self, video_paths: List[str]) -> List[str]:
    #     pass 
    