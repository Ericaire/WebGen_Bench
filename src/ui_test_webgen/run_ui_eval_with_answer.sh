DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../..

in_dir=$1

python src/ui_test_webgen/ui_eval_with_answer.py \
    --in_dir $in_dir