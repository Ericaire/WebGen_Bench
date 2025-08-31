DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../..

in_dir=$1
tag="1"

python src/grade_appearance_webgen/eval_appearance.py $in_dir --tag "$tag"

python src/grade_appearance_webgen/compute_grade.py $in_dir --tag "$tag"