import sys
import os

BROWSER = 'firefox'
OUTFILE = '/tmp/bedshape.html'

infile = sys.argv[1]

bed_shape_coords = None
with open(infile, 'r') as fh:
    for line in fh:
        if line.startswith('bed_shape'):
            if bed_shape_coords:
                raise RuntimeError("found two bed_shape lines!")

            bed_shape_coords = line.split('=',1 )[1].strip()


if not bed_shape_coords:
    raise RuntimeError("bed_shape not found")

with open(OUTFILE, 'w') as fh:
    text_tags = ''
    min_x = 1000
    min_y = 1000
    max_x = -1000
    max_y = -1000
    for i, coords in enumerate(bed_shape_coords.split(',')):
        x, y = coords.split('x')
        text_tags += f'<text font-size="60%" fill="#00000055" x="{x}" y="{y}">{i}</text>'
        min_x = min(min_x, float(x))
        min_y = min(min_y, float(y))
        max_x = max(max_x, float(x))
        max_y = max(max_y, float(y))

    print("X range:", min_x, max_x)
    print("Y range:", min_y, max_y)

    polyline_points = bed_shape_coords.replace(',', ' ').replace('x', ',')
    fh.write(f'''
        <html>
            <svg width="2000" height="2000" viewBox="-400 -400 800 800">
                <polyline points="{polyline_points}" stroke="#0000ff77" fill="#cccccc55" stroke-width="4"/>
                {text_tags}
            </svg>
        </html>
    ''')

os.system(f"{BROWSER} {OUTFILE}")
