#!/bin/bash

BASEPATH='/usr/local/route53'

if [ -f $BASEPATH/dynect.cfg ];then
	echo "Dynect's Route 53 as secondary DNS has been installed."
	echo "If you would like to change or update configuration options, edit:"
	echo "   $BASEPATH/handle_notify.cfg"
	echo "   $BASEPATH/dynect.cfg"
	echo " "
	echo "Press Enter to continue"
	read junk
	exit 1
else
	echo "*****************************************"
	echo "Installing Dynect's Route 53 as secondary DNS files..."
	echo "*****************************************"
	echo ""
	echo "Make sure you have updated the information in:"
	echo "  handle_notify.cfg"
	echo "  dynect.cfg"
	echo "before running this script."
	echo ""
	echo "Enter C to continue with the install or anyhthing else to quit."
	read choice
	if [ $choice != "C" ] && [ $choice != "c" ]; then
		exit 1
	fi
	echo "Which option for syncing Route 53 with Dynect would you like to install? Sync will only occur if zones are different in all cases"
	echo "  1 - Reply to Dynect notify requests"
	echo "  2 - Run a timed sync check"
	echo "  3 - Both - mimics a standard secondary DNS setup"
	read selection
	if [ $selection -eq 2 ] || [ $selection -eq 3 ]; then 
		echo "What interval in minutes would you like to poll for changes on?"
		echo "If you are replying to notify as well the time should be longer, 20 minutes is the shortest reccomended time"
		read minutes
		while ! [[ "$minutes" =~ ^[0-9]+$ ]] ; do
			echo "Minutes must be entered as a number";
		done
	else
		minutes=-1
	fi
	$(sudo mkdir $BASEPATH)
	$(sudo cp handle_notify.py $BASEPATH/handle_notify.py)
	$(sudo cp dynect.py $BASEPATH/dynect.py)
	$(sudo cp route53helper.py $BASEPATH/route53helper.py)
	$(sudo cp sync_route53.py $BASEPATH/sync_route53.py)
	$(sudo cp handle_notify.cfg $BASEPATH/handle_notify.cfg)
	$(sudo cp dynect.cfg $BASEPATH/dynect.cfg)
	$(sudo cp settings.py $BASEPATH/settings.py)
	
	if [ $selection -eq 2 ] || [ $selection -eq 3 ]; then
		hours=$(($minutes/60))
		days=$(($hours/24))
		
		hours=$(($hours%24))
		minutes=$(($minutes%60))
	
		if [ $hours -eq 0 ]; then
			hours="*"
		else
			hours="*/$hours"
		fi

		if [ $days -eq 0 ]; then
			days="*"
		else
			days="*/$days"
		fi

		if [ $minutes -eq 0 ]; then
			minutes="*"
		else
			minutes="*/$minutes"
		fi
	
		$(crontab -l > tempcronfile)
		$(sudo echo "$minutes $hours $days * * $BASEPATH/sync_route53.py" >> tempcronfile)
		$(crontab tempcronfile)
		$(rm tempcronfile)
	fi
	
	if [ $selection -eq 1 ] || [ $selection -eq 3 ]; then
		$(sudo python $BASEPATH/handle_notify.py > startup.txt)
	fi
	
	echo " "
	echo "Install is completed"
fi

