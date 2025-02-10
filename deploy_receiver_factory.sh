source .env
echo "y" | mox deploy UntronReceiverFactory --network $RECEIVER_FACTORY_DEPLOYMENT_NETWORK --private-key $PRIVATE_KEY
echo "y" | mox deploy UntronReceiverFactory --network $RESOLVER_DEPLOYMENT_NETWORK --private-key $PRIVATE_KEY