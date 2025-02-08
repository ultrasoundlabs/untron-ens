source .env
mox build
mox test
echo "y" | mox deploy UntronResolver --network $DEPLOYMENT_NETWORK --private-key $PRIVATE_KEY