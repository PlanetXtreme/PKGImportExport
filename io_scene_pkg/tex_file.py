# ##### BEGIN LICENSE BLOCK #####
#
# This program is licensed under Creative Commons BY-NC-SA:
# https://creativecommons.org/licenses/by-nc-sa/3.0/
#
# Created by Dummiesman, 2016-2020 (2026 edit by Planet Xtreme for MCSR Opacity flags in 2026)
#
# ##### END LICENSE BLOCK #####

from enum import IntEnum
import struct
import bpy

class TEXType(IntEnum):
    P8 = 1
    P8A8 = 2
    A1R5G5B5 = 6
    PA8 = 14
    P4 = 15
    PA4 = 16
    RGB888 = 17
    RGB8888 = 18
    
class TEXFile:
    
    # ==========================================
    # BLENDER INTEGRATION
    # ==========================================
    
    def to_blender_image(self, name='tex_image', pack=True):
        has_alpha = self.has_alpha_channel()
        is_emission = self.is_emission_mask()
        
        im = bpy.data.images.new(name=name, width=self.width, height=self.height, alpha=has_alpha)
        
        # --- THE MAGIC TRICK ---
        im['is_emission_mask'] = is_emission
        
        pixels = list(im.pixels)
        max_alpha = 0.0
        
        for y in range(self.height):
            for x in range(self.width):
                flipped_y = self.height - y - 1
                b_pixel_index = 4 * ((flipped_y * self.width) + x)
                pixel_color = self.get_pixel(x, y)
                
                pixels[b_pixel_index] = pixel_color[0]
                pixels[b_pixel_index+1] = pixel_color[1]
                pixels[b_pixel_index+2] = pixel_color[2]
                
                alpha = pixel_color[3] if has_alpha else 1.0
                pixels[b_pixel_index+3] = alpha
                
                if alpha > max_alpha:
                    max_alpha = alpha
                    
        # 100% Transparent Bug Fix
        if has_alpha and not is_emission and max_alpha == 0.0:
            print(f"[{name}] Detected as 100% transparent! Forcing to fully opaque.")
            for i in range(3, len(pixels), 4):
                pixels[i] = 1.0
    
        im.pixels = pixels[:]
        im.update()
        
        if pack:
            im.pack()
            
        return im

    def from_blender_image(self, image, shader=None):
        """Populates the TEXFile properties and pixel data from a Blender Image."""
        self.width = image.size[0]
        self.height = image.size[1]
        
        # We enforce RGB8888 on export for maximum quality and lossless alpha
        self.format = TEXType.RGB8888
        
        # --- SMART FLAG GENERATION ---
        self.flags = 0
        
        if shader:
            # Check if the material actually emits light (RGB > 0)
            is_emissive = sum(shader.emissive_color[:3]) > 0.001
            # Check if there is an alpha channel present
            has_alpha = image.channels == 4 or image.depth == 32
            
            if has_alpha and is_emissive:
                # Engine treats Alpha as an Emission Mask. Set bits 4 & 8 (12)
                self.flags = 12 
            elif has_alpha and shader.diffuse_color[3] < 1.0:
                # Standard transparency. No opaque flag needed.
                self.flags = 0 
        else:
            # Fallback if no shader context is provided
            if image.get('is_emission_mask', False):
                self.flags = 12
        
        # Extract Blender pixels (stored as a flat float array from bottom-left to top-right)
        pixels = list(image.pixels)
        base_bytes = bytearray()
        
        # We must flip the Y axis so it writes from Top to Bottom
        for y in range(self.height - 1, -1, -1):
            row_start = y * self.width * 4
            row_end = row_start + (self.width * 4)
            row_floats = pixels[row_start:row_end]
            
            # Convert float (0.0-1.0) to byte (0-255) fast
            base_bytes.extend(int(max(0.0, min(1.0, p)) * 255) for p in row_floats)
            
        self._generate_mipmaps(base_bytes)

    def _generate_mipmaps(self, base_bytes):
        """Generates a full chain of Box-Filtered Mipmaps for the engine."""
        self.mipmaps = [base_bytes]
        
        current_width = self.width
        current_height = self.height
        current_mip = base_bytes
        
        while current_width > 1 or current_height > 1:
            next_width = max(1, current_width // 2)
            next_height = max(1, current_height // 2)
            next_mip = bytearray(next_width * next_height * 4)
            
            # Simple Box Sampling downscale
            for y in range(next_height):
                for x in range(next_width):
                    src_y = y * 2
                    src_x = x * 2
                    
                    r, g, b, a = 0, 0, 0, 0
                    samples = 0
                    
                    for dy in range(2):
                        for dx in range(2):
                            if src_x + dx < current_width and src_y + dy < current_height:
                                idx = ((src_y + dy) * current_width + (src_x + dx)) * 4
                                r += current_mip[idx]
                                g += current_mip[idx+1]
                                b += current_mip[idx+2]
                                a += current_mip[idx+3]
                                samples += 1
                                
                    dst_idx = (y * next_width + x) * 4
                    next_mip[dst_idx] = r // samples
                    next_mip[dst_idx+1] = g // samples
                    next_mip[dst_idx+2] = b // samples
                    next_mip[dst_idx+3] = a // samples
                    
            self.mipmaps.append(next_mip)
            current_mip = next_mip
            current_width = next_width
            current_height = next_height


    def has_alpha_channel(self):
        return self.format != TEXType.P8 and self.format != TEXType.P4 and self.format != TEXType.RGB888

    def is_emission_mask(self):
        return self.has_alpha_channel() and bool(self.flags & 12)
        
    def __read_palette(self, file, color_count):
        for x in range(color_count):
            col_data = file.read(4)
            self.palette.append((col_data[2] / 255, col_data[1] / 255, col_data[0] / 255, col_data[3] / 255)) 
    
    def __make_palette_opaque(self):
        for i in range(len(self.palette)):
            pal_color = list(self.palette[i])
            pal_color[3] = 1.0
            self.palette[i] = tuple(pal_color)
    
    def is_paletted_format(self):
        return self.format != TEXType.RGB888 and self.format != TEXType.RGB8888 and self.format != TEXType.A1R5G5B5
        
    def is_valid(self):
        return self.width != 0 and self.height != 0 and len(self.mipmaps) > 0
        
    def get_stride(self):
        strides = (0, 1, 2, None, None, None, 2, None, None, None, None, None, None, None, 1, -2, -2, 3, 4)
        fmt_int = int(self.format)
        if fmt_int >= 0 and fmt_int <= 18:
            return strides[fmt_int]
        raise Exception("A wild texture format has appeared")
            
    def calculate_mip_size(self, mipIndex):
        if mipIndex < 0:
            raise Exception("mipIndex must not be < 0")
        mip = 0
        width = self.width
        height = self.height
        while mip != mipIndex:
            width //= 2
            height //= 2
            mip += 1
        return (width, height)

    def calculate_mip_array_size(self, mipIndex):
        size = self.calculate_mip_size(mipIndex)
        stride = self.get_stride()
        retval = (size[0] * size[1]) // -stride if stride < 0 else (size[0] * size[1]) * stride
        return retval


    
    def __get_pixel_pa4_p4(self, x, y, stride, mip_data, mip_size, data_index):
        nibbles = mip_data[data_index]
        nibble1 = nibbles & 0x0F
        nibble2 = (nibbles & 0xF0) >> 4
        nibbleIdx = (x / -stride) + (y * (mip_size[0]  / -stride))
        return self.palette[nibble2] if nibbleIdx > 0 else self.palette[nibble1]
        
    def __get_pixel_pa8_p8(self, x, y, stride, mip_data, mip_size, data_index):
        pal_index = mip_data[data_index]
        return self.palette[pal_index]
        
    def __get_pixel_p8a8(self, x, y, stride, mip_data, mip_size, data_index):
        pal_index = mip_data[data_index]
        alpha = mip_data[data_index + 1]
        color = self.palette[pal_index]
        return (color[0], color[1], color[2], alpha / 255)
       
    def __get_pixel_rgb888(self, x, y, stride, mip_data, mip_size, data_index):
        return (mip_data[data_index] / 255, mip_data[data_index + 1] / 255, mip_data[data_index + 2] / 255, 1.0)
        
    def __get_pixel_rgb8888(self, x, y, stride, mip_data, mip_size, data_index):
        return (mip_data[data_index] / 255, mip_data[data_index + 1] / 255, mip_data[data_index + 2] / 255, mip_data[data_index + 3] / 255)
        
    def __get_pixel_a1r5g5b5(self, x, y, stride, mip_data, mip_size, data_index):
        color_short = struct.unpack('<H', (mip_data[data_index], mip_data[data_index + 1]))[0]
        maskA = 32768 
        maskR = 0x7C00
        maskG = 0x3E0
        maskB = 0x1F

        alpha = ((maskA & color_short) >> 8)
        red = ((maskR & color_short) >> 7)
        green = ((maskG & color_short) >> 2)
        blue = ((maskB & color_short) << 3)
        alpha = 255 if alpha > 0 else 0

        red = red | 0xF if (red & 0x8) == 0x8 else red
        green = green | 0xF if (red & 0x8) == 0x8 else green
        blue = blue | 0xF if (red & 0x8) == 0x8 else blue

        return (red / 255, green / 255, blue / 255, alpha / 255)
        
    def get_pixel(self, x, y, mip_level = 0):
        mip_data = self.mipmaps[mip_level]
        mip_size = self.calculate_mip_size(mip_level)
        stride = self.get_stride()
        
        data_index =  (x * stride) + (y * (mip_size[0] * stride)) if stride > 0 else (x // -stride) + (y * (mip_size[0] // -stride))

        get_pixel_functions = (None, self.__get_pixel_pa8_p8, self.__get_pixel_p8a8, None, None, None, self.__get_pixel_a1r5g5b5, None, None, None, None, None, None, None, self.__get_pixel_pa8_p8, self.__get_pixel_pa4_p4, self.__get_pixel_pa4_p4, self.__get_pixel_rgb888, self.__get_pixel_rgb8888)

        fmt_int = int(self.format)
        if fmt_int >= 0 and fmt_int <= 18:
            return get_pixel_functions[fmt_int](x, y, stride, mip_data, mip_size, data_index)
        else:
            return (0, 0, 0, 0)


    # IO OPERATIONS

    def read(self, filepath):
        with open(filepath, 'rb') as file:
            width, height, format = struct.unpack('<HHH', file.read(6))
            self.width = width
            self.height = height
            self.format = TEXType(format)
            
            mipcount, garbage, self.flags = struct.unpack('<HHL', file.read(8))
            
            if self.format == TEXType.P4 or self.format == TEXType.PA4:
                self.__read_palette(file, 16)
            elif self.format == TEXType.P8A8 or self.format == TEXType.PA8 or self.format == TEXType.P8:
                self.__read_palette(file, 256)
                
            if not self.has_alpha_channel() and self.is_paletted_format():
                self.__make_palette_opaque()
             
            for i in range(mipcount):
                mip_data_size = self.calculate_mip_array_size(i)
                if mip_data_size == 0:
                    break
                data = file.read(mip_data_size)
                self.mipmaps.append(data)

    def write(self, filepath):
        """Writes the TEXFile out to binary."""
        if not self.is_valid():
            raise Exception("Cannot write invalid TEX data. Missing dimensions or mipmaps.")
            
        with open(filepath, 'wb') as file:
            # Header
            file.write(struct.pack('<HHH', self.width, self.height, int(self.format)))
            
            # Mip Count & Flags
            file.write(struct.pack('<HHL', len(self.mipmaps), 0, self.flags))
            
            # Write Palette
            if self.is_paletted_format():
                for color in self.palette:
                    r = int(color[0] * 255)
                    g = int(color[1] * 255)
                    b = int(color[2] * 255)
                    a = int(color[3] * 255)
                    # Game expects BGRA
                    file.write(struct.pack('BBBB', b, g, r, a))
                    
            # 4. Write Mipmaps
            for mip in self.mipmaps:
                file.write(mip)

    def __init__(self, filepath=None):
        self.palette = []
        self.width = 0
        self.height = 0
        self.format = TEXType.RGB8888
        self.flags = 0 
        self.mipmaps = []
        
        if filepath is not None:
            self.read(filepath)