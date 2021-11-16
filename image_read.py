'''
Preprocessing and image reading functions
'''
import torch
import numpy as np
import SimpleITK as sitk
import multiprocessing as mp
from torch.utils.data import Dataset, DataLoader
from torchvision.transforms import Resize, InterpolationMode


class SliceDataset(Dataset):
    def __init__(self, input_path):
        '''
        Treat a volume (input_path) as a dataset of slices.

        input_path: input_path to main image
        '''
        super().__init__()
        self.input_path = input_path
        image = self.read_image()
        data = sitk.GetArrayFromImage(image)
        self.original_shape = data.shape
        
        self.directions = image.GetDirection()
        dir_array = np.asarray(self.directions)
        self.origin = image.GetOrigin()
        self.spacing = image.GetSpacing()

        print(f"Directions: {self.directions}")
        print(f"Origin: {self.origin}")
        print(f"Spacing: {self.spacing}")

        if len(dir_array) == 9:
            data = np.flip(data, np.where(dir_array[[0,4,8]][::-1]<0)[0]).copy()  # fix axial orientation for bed on the bottom

        # Pre processing
        data = np.clip(data, -1024, 600)
        data = (data - data.min()) / (data.max() - data.min())

        data = torch.from_numpy(data)
        data = data.unsqueeze(1)  # [Fatia, H, W] -> [Fatia, 1, H, W]
        
        self.data = data
        self.transform = Resize((512, 512), interpolation=InterpolationMode.BILINEAR)

    def __len__(self):
        return self.data.shape[0]

    def __getitem__(self, i):
        data = self.data[i]
        
        transformed_data = self.transform(data)
        
        return transformed_data 

    def get_header(self):
        return self.header

    def get_affine(self):
        return self.affine

    def read_image(self):
        return sitk.ReadImage(self.input_path)

    def get_dataloader(self, batch_size):
        return DataLoader(self, batch_size=batch_size, pin_memory=True, shuffle=False, num_workers=mp.cpu_count())
