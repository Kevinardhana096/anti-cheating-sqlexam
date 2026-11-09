"""Validate a bounded image batch before writing any public files."""
from io import BytesIO
from pathlib import Path
import uuid
import warnings
from PIL import Image
from fastapi import HTTPException

MAX_FILE_BYTES=8*1024*1024
MAX_BATCH_BYTES=32*1024*1024
MAX_PIXELS=20_000_000
MAX_FILES=20


async def store(files,static_dir,image_type):
    if not 1<=len(files)<=MAX_FILES:
        raise HTTPException(422,'Unggah 1 sampai 20 gambar per permintaan.')
    validated=[];total=0
    formats={'PNG':'.png','JPEG':'.jpg','WEBP':'.webp','GIF':'.gif'}
    for file in files:
        if Path(file.filename or '').suffix.lower() not in {'.png','.jpg','.jpeg','.webp','.gif'}:
            raise HTTPException(422,'Gunakan PNG, JPG, WEBP atau GIF. SVG tidak diterima.')
        content=await file.read(MAX_FILE_BYTES+1)
        total+=len(content)
        if len(content)>MAX_FILE_BYTES or total>MAX_BATCH_BYTES:
            raise HTTPException(413,'Batas gambar 8 MiB; total batch 32 MiB.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as img:
                    if img.format not in formats or img.width*img.height>MAX_PIXELS:
                        raise ValueError('format/dimensi')
                    extension=formats[img.format]
                    img.verify()
                # Decode every frame, not just a plausible header.
                with Image.open(BytesIO(content)) as img:
                    for n in range(getattr(img,'n_frames',1)):
                        img.seek(n);img.load()
                        if (n+1)*img.width*img.height>MAX_PIXELS:
                            raise ValueError('total dimensi frame')
        except Exception as error:
            raise HTTPException(422,'Berkas gambar rusak atau dimensinya melebihi batas.') from error
        prefix='qimg' if image_type=='question' else 'output'
        validated.append((prefix+'_'+uuid.uuid4().hex+extension,content))
    directory=(Path(static_dir)/'uploads/questions').resolve()
    directory.mkdir(parents=True,exist_ok=True)
    written=[]
    try:
        for name,content in validated:
            path=(directory/name).resolve()
            if path.parent!=directory:
                raise ValueError('Lokasi unggahan tidak valid.')
            with path.open('xb') as output:
                written.append(path)
                output.write(content)
    except Exception:
        for path in written:
            if path.parent==directory and path.is_file():
                path.unlink()
        raise HTTPException(500,'Gagal menyimpan gambar; batch dibatalkan.')
    return ['/static/uploads/questions/'+name for name,_ in validated]
