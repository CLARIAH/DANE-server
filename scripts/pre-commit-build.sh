#!/bin/sh

# run this to install dane-workflows from github
if poetry remove dane; then
    echo "successfully uninstalled dane"
else
    echo "dane already uninstalled"
fi

poetry add dane