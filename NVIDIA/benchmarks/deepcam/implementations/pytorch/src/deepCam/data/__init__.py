# The MIT License (MIT)
#
# Copyright (c) 2020-2023 NVIDIA CORPORATION. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE. 

import os
from glob import glob
import torch

from torch.utils.data import Dataset
from torch.utils.data import DataLoader
from torch.utils.data import DistributedSampler

# regular datasets
from .cam_hdf5_dataset import CamDataset
from .cam_numpy_dali_dataset import CamDaliNumpyDataloader
from .cam_recordio_dali_dataset import CamDaliRecordIODataloader
from .cam_es_dali_dataset import CamDaliESDataloader
from .cam_es_dali_gpu_dataset import CamDaliESGPUDataloader
from .cam_es_disk_dali_dataset import CamDaliESDiskDataloader
from .dummy_dali_dataset import DummyDaliDataloader

# fused datasets
from .cam_numpy_dali_fused_dataset import CamDaliNumpyFusedDataloader
from .cam_es_dali_fused_dataset import CamDaliESFusedDataloader
from .cam_es_dali_gpu_fused_dataset import CamDaliESGPUFusedDataloader  

# common stuff
from .common import get_datashapes
    
        
# helper function to de-clutter the main training script
def get_dataloaders(pargs, root_dir, device, seed, comm_size, comm_rank):
    
    if pargs.data_format == "hdf5":
        train_dir = os.path.join(root_dir, "train")
        train_set = CamDataset(train_dir, 
                               statsfile = os.path.join(root_dir, 'stats.h5'),
                               channels = pargs.channels,
                               allow_uneven_distribution = False,
                               shuffle = True, 
                               preprocess = True,
                               transpose = not pargs.enable_nhwc,
                               augmentations = pargs.data_augmentations,
                               num_shards = 1,
                               shard_id = 0)

        distributed_train_sampler = DistributedSampler(train_set,
                                                       num_replicas = comm_size,
                                                       rank = comm_rank,
                                                       shuffle = True,
                                                       drop_last = True)
    
        train_loader = DataLoader(train_set,
                                  pargs.local_batch_size,
                                  num_workers = min([pargs.data_num_threads, pargs.local_batch_size]),
                                  sampler = distributed_train_sampler,
                                  pin_memory = True,
                                  drop_last = True)

        train_size = train_set.global_size

    else:
        fused = False
        oversampling_factor=1
        kwargs={}
        if pargs.data_format == "dali-numpy":
            dl_handle = CamDaliNumpyDataloader
            data_filter = 'data-*.npy'
            label_filter = 'label-*.npy'
        elif pargs.data_format == "dali-numpy-fused":
            dl_handle = CamDaliNumpyFusedDataloader
            datalabel_filter = 'datalabel-*.npy'
            fused = True
        elif pargs.data_format == "dali-dummy":
            dl_handle = DummyDaliDataloader
            data_filter = None
            label_filter = None
        elif pargs.data_format == "dali-recordio":
            dl_handle = CamDaliRecordIODataloader
            data_filter = 'data-*.rec'
            label_filter = 'label-*.rec'
        elif pargs.data_format == 'dali-es':
            dl_handle = CamDaliESDataloader
            data_filter = 'data-*.npy'
            label_filter = 'label-*.npy'
            oversampling_factor = pargs.data_oversampling_factor
        elif pargs.data_format == 'dali-es-fused':
            dl_handle = CamDaliESFusedDataloader
            datalabel_filter = 'datalabel-*.npy'
            oversampling_factor = pargs.data_oversampling_factor
            fused = True
        elif pargs.data_format == 'dali-es-gpu':
            dl_handle = CamDaliESGPUDataloader
            data_filter = 'data-*.npy'
            label_filter = 'label-*.npy'
            oversampling_factor = pargs.data_oversampling_factor
        elif pargs.data_format == 'dali-es-gpu-fused':
            dl_handle = CamDaliESGPUFusedDataloader
            datalabel_filter = 'datalabel-*.npy'
            oversampling_factor = pargs.data_oversampling_factor
            fused = True
        elif pargs.data_format == 'dali-es-disk':
            dl_handle = CamDaliESDiskDataloader
            data_filter = 'data-*.npy'
            label_filter = 'label-*.npy'
            oversampling_factor = pargs.data_oversampling_factor
            kwargs = dict(cache_directory = os.path.join(pargs.data_cache_directory, "train"))
            
        train_dir = os.path.join(root_dir, "train")
        if not fused:
            
            train_loader = dl_handle(train_dir,
                                     data_filter,
                                     label_filter,
                                     os.path.join(root_dir, 'stats.h5'),
                                     pargs.local_batch_size,
                                     file_list_data = "files_data.lst",
                                     file_list_label = "files_label.lst",
                                     num_threads = pargs.data_num_threads,
                                     device = device,
                                     num_shards = comm_size,
                                     shard_id = comm_rank,
                                     shuffle_mode = pargs.shuffle_mode,
                                     oversampling_factor = oversampling_factor,
                                     is_validation = False,
                                     lazy_init = True,
                                     transpose = not pargs.enable_nhwc,
                                     augmentations = pargs.data_augmentations,
                                     read_gpu = pargs.enable_gds,
                                     use_mmap = pargs.enable_mmap,
                                     use_odirect = pargs.enable_odirect,
                                     seed = seed, **kwargs)
        else:
            
            train_loader = dl_handle(train_dir,
                                     datalabel_filter,
                                     os.path.join(root_dir, 'stats.h5'),
                                     pargs.local_batch_size,
                                     file_list_datalabel = "files_datalabel.lst",
                                     num_threads = pargs.data_num_threads,
                                     device = device,
                                     num_shards = comm_size,
                                     shard_id = comm_rank,
                                     shuffle_mode = pargs.shuffle_mode,
                                     oversampling_factor = oversampling_factor,
                                     is_validation = False,
                                     lazy_init = True,
                                     transpose = not pargs.enable_nhwc,
                                     augmentations = pargs.data_augmentations,
                                     read_gpu = pargs.enable_gds,
                                     use_mmap = pargs.enable_mmap,
                                     use_odirect = pargs.enable_odirect,
                                     seed = seed, **kwargs)
        train_size = train_loader.global_size
    
    # validation: we only want to shuffle the set if we are cutting off validation after a certain number of steps
    if pargs.data_format == "hdf5":
        validation_dir = os.path.join(root_dir, "validation")
        validation_set = CamDataset(validation_dir, 
                                    statsfile = os.path.join(root_dir, 'stats.h5'),
                                    channels = pargs.channels,
                                    allow_uneven_distribution = True,
                                    shuffle = False,
                                    preprocess = True,
                                    transpose = not pargs.enable_nhwc,
                                    augmentations = [],
                                    num_shards = comm_size,
                                    shard_id = comm_rank)
    
        # use batch size = 1 here to make sure that we do not drop a sample
        validation_loader = DataLoader(validation_set,
                                       1,
                                       num_workers = min([pargs.data_num_threads, pargs.local_batch_size]),
                                       pin_memory = True,
                                       drop_last = False)

        validation_size = validation_set.global_size
        
    else:
        fused = False
        kwargs={}
        if (pargs.data_format in ["dali-numpy", "dali-es", "dali-es-disk", "dali-es-gpu"]):
            dl_handle = CamDaliNumpyDataloader
            data_filter='data-*.npy'
            label_filter='label-*.npy'
        elif (pargs.data_format in ["dali-numpy-fused", "dali-es-fused", "dali-es-gpu-fused"]):
            dl_handle = CamDaliNumpyFusedDataloader
            datalabel_filter='datalabel-*.npy'
            fused = True
        elif pargs.data_format == "dali-dummy":
            dl_handle = DummyDaliDataloader
        elif pargs.data_format == "dali-recordio":
            dl_handle = CamDaliRecordIODataloader
            data_filter='data-*.rec'
            label_filter='label-*.rec'
            
        validation_dir = os.path.join(root_dir, "validation")
        if not fused:
            validation_loader = dl_handle(validation_dir,
                                          data_filter,
                                          label_filter,
                                          os.path.join(root_dir, 'stats.h5'),
                                          pargs.local_batch_size_validation,
                                          file_list_data = "files_data.lst",
                                          file_list_label = "files_label.lst",
                                          num_threads = pargs.data_num_threads,
                                          device = device,
                                          num_shards = comm_size,
                                          shard_id = comm_rank,
                                          shuffle_mode = None,
                                          is_validation = True,
                                          lazy_init = True,
                                          transpose = not pargs.enable_nhwc,
                                          augmentations = [],
                                          read_gpu = pargs.enable_gds,
                                          use_mmap = False,
                                          use_odirect = False,
                                          seed = seed, **kwargs)
        else:
            validation_loader = dl_handle(validation_dir,
                                          datalabel_filter,
                                          os.path.join(root_dir, 'stats.h5'),
                                          pargs.local_batch_size_validation,
                                          file_list_datalabel = "files_datalabel.lst",
                                          num_threads = pargs.data_num_threads,
                                          device = device,
                                          num_shards = comm_size,
                                          shard_id = comm_rank,
                                          shuffle_mode = None,
                                          is_validation = True,
                                          lazy_init = True,
                                          transpose = not pargs.enable_nhwc,
                                          augmentations = [],
                                          read_gpu = pargs.enable_gds,
                                          use_mmap = False,
                                          use_odirect =	False,
                                          seed = seed, **kwargs)
        validation_size = validation_loader.global_size
    
        
    return train_loader, train_size, validation_loader, validation_size
