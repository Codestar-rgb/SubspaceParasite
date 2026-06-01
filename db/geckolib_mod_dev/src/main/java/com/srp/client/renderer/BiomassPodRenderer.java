package com.srp.client.renderer;

import com.srp.client.model.BiomassPodModel;
import com.srp.entity.BiomassPodEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class BiomassPodRenderer extends GeoEntityRenderer<BiomassPodEntity> {

    public BiomassPodRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new BiomassPodModel());
    }
}
